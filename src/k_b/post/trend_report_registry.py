"""The register of the trend reports, trend_reports.json in KB_DATA_DIR: one entry per report
written, the last one giving the next report its period (docs/tendances.md, "Registre des comptes
rendus"). The vault is never read back to find it.

Limit: two runs that overlap each add their entry to the list they read, and the last one written
wins, as for the vault (post/vault_files.py)."""

from pathlib import Path
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    TypeAdapter,
    ValidationError,
    model_validator,
)

from k_b.core.atomic_write import write_file_atomically
from k_b.core.config import MODEL_NAME
from k_b.core.quoting import locate_first_error
from k_b.items import UtcDatetime, WrittenDayInStrictModel, has_too_many_windows
from k_b.post.ai_api_client import REQUEST_ID, match_fully

TREND_REPORTS_FILENAME = "trend_reports.json"


class InvalidTrendRegistryError(Exception):
    """The register cannot be read, or is out of its schema: no report is asked."""


class TrendReportEntry(BaseModel):
    """A report written: its windows, the missing ones included, its file in the vault, when it
    was written, and the request, the model and the choice it came from."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    first_window: WrittenDayInStrictModel
    last_window: WrittenDayInStrictModel
    file: str
    written_at: UtcDatetime
    request_id: Annotated[str, AfterValidator(match_fully(REQUEST_ID))]
    # Null and false until a model chooses the repositories (#368).
    model: Annotated[str, AfterValidator(match_fully(MODEL_NAME))] | None
    choice_made: bool

    @model_validator(mode="after")
    def check_windows(self) -> Self:
        """In order, and as many as a report holds: the next request would be refused."""
        if self.first_window > self.last_window:
            raise ValueError("first_window is after last_window")
        if has_too_many_windows(self.first_window, self.last_window):
            raise ValueError("more windows than a report holds")
        return self


REGISTER = TypeAdapter(list[TrendReportEntry])


def load_trend_reports(data_dir: Path) -> list[TrendReportEntry]:
    """The entries in the order they were written; empty when the register is absent."""
    try:
        content = (data_dir / TREND_REPORTS_FILENAME).read_bytes()
    except FileNotFoundError:
        return []
    except OSError as error:
        # The type and the reason, never the path, which names the data folder.
        raise InvalidTrendRegistryError(
            f"{TREND_REPORTS_FILENAME} not read: {type(error).__name__} ({error.strerror})"
        ) from None
    try:
        return REGISTER.validate_json(content)
    except ValidationError as error:
        raise InvalidTrendRegistryError(
            f"{TREND_REPORTS_FILENAME} invalid: {locate_first_error(error)}"
        ) from None


def append_trend_report(
    data_dir: Path, entries: list[TrendReportEntry], entry: TrendReportEntry
) -> None:
    """Write the register again, entry after the entries read at the start of the run."""
    content = REGISTER.dump_json([*entries, entry], indent=2) + b"\n"
    write_file_atomically(data_dir / TREND_REPORTS_FILENAME, content)
