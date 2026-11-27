"""The digests of the watch in the vault: one Markdown sheet per subject and per day, and its twin
in JSON for the data API (#560), written once by kb digest from the response of the AI API, with
the limit of post/vault_files.py.

Its path is made of constants, a subject of the closed list and a day; each text of the response
is written as text, as the response is untrusted (OWASP LLM10)."""

import json
import re
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

from k_b.core.config import SHEET_TWIN_SUFFIX, WATCH_DIR_NAME
from k_b.core.dates import format_date
from k_b.items import (
    DigestOutcome,
    DigestProduction,
    convert_to_utc,
    is_writable_url,
    make_visible,
    parse_aware_datetime,
)
from k_b.post.ai_api_client import Digest, DigestsResponse, Source
from k_b.post.vault_files import (
    VaultEntryRefusedError,
    has_sheet,
    list_sheet_names,
    neutralize_digest_text,
    read_sheet_head,
    refuse_linked_folders,
    write_new_sheet,
)

NO_CLAIM = "Aucune affirmation retenue."
NO_ITEM = "Aucun item classé dans ce sujet."
# The name of a sheet kb writes: a note of Sabine or a temporary file in the folder is not one.
SHEET_NAME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.md")
# The front matter opens a sheet; these bytes hold it whole, read without the rest of the sheet.
MAX_FRONT_MATTER_BYTES = 4096
FRONT_MATTER_OPENING = b"---\n"
FRONT_MATTER_CLOSING = b"\n---\n"
UNTIL_KEY = "until: "


def find_sheets_dir(vault_dir: Path, subject: str) -> Path:
    return vault_dir / WATCH_DIR_NAME / subject


def find_sheet_path(vault_dir: Path, subject: str, day: date) -> Path:
    return find_sheets_dir(vault_dir, subject) / f"{day.isoformat()}.md"


def find_twin_path(vault_dir: Path, subject: str, day: date) -> Path:
    return find_sheets_dir(vault_dir, subject) / f"{day.isoformat()}{SHEET_TWIN_SUFFIX}"


def refuse_written_sheets(
    vault_dir: Path, subject_names: Sequence[str], day: date
) -> None:
    """Before the request, refuse a sheet or a twin of a subject already written for day, or a
    folder down to it that is a symbolic link; creates nothing."""
    for subject in subject_names:
        sheets_dir = find_sheets_dir(vault_dir, subject)
        refuse_linked_folders(vault_dir, sheets_dir)
        refuse_existing_sheet(find_sheet_path(vault_dir, subject, day), vault_dir)
        twin_path = find_twin_path(vault_dir, subject, day)
        if has_sheet(twin_path, vault_dir):
            raise find_twin_exists_error(twin_path, vault_dir)


def refuse_existing_sheet(sheet_path: Path, vault_dir: Path) -> None:
    if has_sheet(sheet_path, vault_dir):
        raise find_sheet_exists_error(sheet_path, vault_dir)


def find_sheet_exists_error(
    sheet_path: Path, vault_dir: Path
) -> VaultEntryRefusedError:
    return VaultEntryRefusedError(
        f"sheet_exists: {sheet_path.relative_to(vault_dir).as_posix()} is there;"
        " kb digest never rewrites a sheet"
    )


def find_twin_exists_error(twin_path: Path, vault_dir: Path) -> VaultEntryRefusedError:
    return VaultEntryRefusedError(
        f"twin_exists: {twin_path.relative_to(vault_dir).as_posix()} is there;"
        " kb digest never rewrites a twin"
    )


def read_subject_starts(
    vault_dir: Path, subject_names: Sequence[str], now: datetime
) -> dict[str, datetime]:
    """The start of each subject with a sheet: the until of its last sheet."""
    starts: dict[str, datetime] = {}
    for subject in subject_names:
        until = find_previous_until(vault_dir, subject, now)
        if until is not None:
            starts[subject] = until
    return starts


def find_previous_until(
    vault_dir: Path, subject: str, now: datetime
) -> datetime | None:
    """The until of the last sheet of subject, the one of the greatest day; None without a sheet.
    A last sheet that is a link, or without one valid until up to now, is refused."""
    sheets_dir = find_sheets_dir(vault_dir, subject)
    names = list_sheet_names(sheets_dir, SHEET_NAME)
    if not names:
        return None
    sheet_path = sheets_dir / max(names)
    # Refuses a link or another entry under the name of the sheet, read by lstat.
    has_sheet(sheet_path, vault_dir)
    until = read_until(read_sheet_head(sheet_path, vault_dir, MAX_FRONT_MATTER_BYTES))
    if until is None or until > now:
        raise VaultEntryRefusedError(
            f"previous_sheet_invalid: {sheet_path.relative_to(vault_dir).as_posix()} has no"
            " until in its front matter that is a date with its zone, up to now"
        )
    return until


def read_until(head: bytes) -> datetime | None:
    """The until of the front matter that opens head, in UTC to its second as kb sends it; None
    when the front matter is not there, or holds none or more than one until that is a date."""
    end = head.find(FRONT_MATTER_CLOSING)
    if not head.startswith(FRONT_MATTER_OPENING) or end == -1:
        return None
    try:
        lines = head[len(FRONT_MATTER_OPENING) : end].decode("utf-8").split("\n")
    except UnicodeDecodeError:
        return None
    values = [
        line.removeprefix(UNTIL_KEY) for line in lines if line.startswith(UNTIL_KEY)
    ]
    if len(values) != 1:
        return None
    try:
        until = convert_to_utc(parse_aware_datetime(values[0], "until"))
    except ValueError:
        return None
    return until.replace(microsecond=0)


def write_digest_sheet(
    vault_dir: Path, response: DigestsResponse, digest: Digest
) -> str:
    """Write the sheet of digest, of the UTC day of the end of the window; return its path in the
    vault. A sheet written meanwhile is refused (sheet_exists), and one another run is writing
    (temporary_file_found): neither is replaced, with the limits of post/vault_files.py."""
    return write_sheet(
        vault_dir, response, digest.subject, render_digest_sheet(response, digest)
    )


def write_empty_sheet(vault_dir: Path, response: DigestsResponse, subject: str) -> str:
    """Write the sheet of a subject no item fell in, as write_digest_sheet: its until is the start
    of the next digest of the subject."""
    return write_sheet(
        vault_dir, response, subject, render_empty_sheet(response, subject)
    )


def write_sheet(
    vault_dir: Path, response: DigestsResponse, subject: str, content: str
) -> str:
    sheet_path = find_sheet_path(vault_dir, subject, response.window.until.date())
    if not write_new_sheet(
        vault_dir, find_sheets_dir(vault_dir, subject), sheet_path, content
    ):
        # Seen by write_new_sheet: refused on that one look, never looked at again.
        raise find_sheet_exists_error(sheet_path, vault_dir)
    return sheet_path.relative_to(vault_dir).as_posix()


def build_digest_twin(
    response: DigestsResponse, subject: str, digest: Digest | None
) -> DigestProduction:
    """The twin of the sheet of subject, digest None for a subject without items: what the sheet
    says, each text visible on one line, each source with its item_id; a ValidationError when its
    schema refuses it."""
    window = response.window
    claims = [] if digest is None else digest.claims
    return DigestProduction.model_validate(
        {
            "subject": subject,
            "since": response.since_by_subject[subject],
            "until": window.until,
            "model": response.model,
            "items_capped": response.items_capped,
            "capped_kind": window.capped_kind,
            "covered_after": window.covered_after,
            "outcome": find_outcome(digest),
            "claims": [
                {"text": make_visible(claim.text), "item_ids": list(claim.item_ids)}
                for claim in claims
            ],
            # As the sheet: no source without a claim.
            "sources": [
                build_twin_source(source)
                for source in ([] if digest is None or not claims else digest.sources)
            ],
        }
    )


def find_outcome(digest: Digest | None) -> DigestOutcome:
    if digest is None:
        return "no_item"
    return "written" if digest.claims else "no_claim"


def build_twin_source(source: Source) -> dict[str, object]:
    return {
        "item_id": source.item_id,
        "title": make_visible(source.title),
        "url": find_writable_url(source),
    }


def write_digest_twin(vault_dir: Path, twin: DigestProduction) -> str:
    """Write the twin beside the sheet of its subject and of the day of its until; return its path
    in the vault. A twin there is refused (twin_exists), never replaced."""
    twin_path = find_twin_path(vault_dir, twin.subject, twin.until.date())
    if not write_new_sheet(
        vault_dir,
        find_sheets_dir(vault_dir, twin.subject),
        twin_path,
        twin.model_dump_json(),
    ):
        raise find_twin_exists_error(twin_path, vault_dir)
    return twin_path.relative_to(vault_dir).as_posix()


def render_empty_sheet(response: DigestsResponse, subject: str) -> str:
    return "\n".join([*render_heading(response, subject), NO_ITEM]) + "\n"


def render_heading(response: DigestsResponse, subject: str) -> list[str]:
    """The front matter of a sheet, then its title; since is the start of its subject."""
    window = response.window
    return [
        "---",
        f"subject: {subject}",
        f"generated: {format_date(window.until)}",
        # Checked by MODEL_NAME; written as a string of JSON, which YAML reads as it is.
        f"model: {json.dumps(response.model)}",
        f"since: {format_date(response.since_by_subject[subject])}",
        f"until: {format_date(window.until)}",
        f"items_capped: {json.dumps(response.items_capped)}",
        # A kind of the closed list (ItemKind) and a date: null when nothing is cut.
        f"capped_kind: {window.capped_kind or 'null'}",
        f"covered_after: {format_date(window.covered_after) or 'null'}",
        f"request_id: {response.request_id}",
        "---",
        "",
        f"# Veille {subject} du {window.until.date().isoformat()}",
        "",
    ]


def render_digest_sheet(response: DigestsResponse, digest: Digest) -> str:
    """The Markdown of a sheet: a front matter, the claims citing their sources by number, then
    the sources; the same response gives the same bytes."""
    lines = render_heading(response, digest.subject)
    if not digest.claims:
        return "\n".join([*lines, NO_CLAIM]) + "\n"
    number_by_item = {
        source.item_id: number for number, source in enumerate(digest.sources, start=1)
    }
    lines += [
        f"- {neutralize_digest_text(claim.text)}"
        f" ({cite_sources(sorted(number_by_item[item_id] for item_id in claim.item_ids))})"
        for claim in digest.claims
    ]
    lines += ["", "## Sources", ""]
    lines += [
        f"{number}. {render_source(source)}"
        for number, source in enumerate(digest.sources, start=1)
    ]
    return "\n".join(lines) + "\n"


def cite_sources(numbers: list[int]) -> str:
    listed = ", ".join(str(number) for number in numbers)
    return f"source {listed}" if len(numbers) == 1 else f"sources {listed}"


def render_source(source: Source) -> str:
    title = neutralize_digest_text(source.title)
    url = find_writable_url(source)
    if url is None:
        return f"{title} (sans URL)"
    return f"{title} — <{url}>"


def find_writable_url(source: Source) -> str | None:
    """The URL of the source the sheet writes as a link, and its twin serves; None otherwise."""
    if source.url is None or not is_writable_url(source.url):
        return None
    return source.url
