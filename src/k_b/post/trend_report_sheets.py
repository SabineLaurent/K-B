"""The trend reports in the vault: one Markdown file per day of a run, veille/tendances/<day>.md,
written once by kb trend-report from the response of the AI API, with the limit of
post/vault_files.py.

Each text is made by the code from checked values: a day, a count, a word of a closed list, and
the name of a repository, checked by is_repository_name, which makes its URL. No text of the
response is free, so none needs neutralize_digest_text, which would break a URL (www. escaped)."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

from k_b.core.config import (
    GH_ARCHIVE_MAX_CATCH_UP_WINDOWS,
    GH_ARCHIVE_WINDOW_DAYS,
    TRENDS_DIR_NAME,
    WATCH_DIR_NAME,
)
from k_b.core.dates import format_date
from k_b.items import Criterion
from k_b.post.trend_report_client import (
    TrendPeriod,
    TrendPoint,
    TrendReportResponse,
    TrendRepository,
)
from k_b.post.vault_files import (
    VaultEntryRefusedError,
    has_sheet,
    refuse_linked_folders,
    write_new_sheet,
)

GITHUB_URL = "https://github.com/"
CRITERION_LABELS: dict[Criterion, str] = {
    "durable": "durable",
    "new": "nouveau",
    "accelerating": "en accélération",
}
OUT_OF_TOP = "hors top"
MISSING = "—"
# The limit of the counts (docs/tendances.md, "Limite de GH Archive"): never stars gained alone.
GH_ARCHIVE_LIMIT = (
    "Les comptes viennent de GH Archive, un échantillon d'environ 1 % des étoiles données sur"
    " GitHub (mesure du 2026-10-29) : des rangs proches ne se départagent pas."
)
NO_REPOSITORY = "Aucun dépôt ne remplit un critère sur la période."
TABLE_HEADER = (
    "| Dépôt | Critères | Meilleur rang | Trajectoire (rang par fenêtre) |",
    "|---|---|---|---|",
)


def find_sheets_dir(vault_dir: Path) -> Path:
    return vault_dir / WATCH_DIR_NAME / TRENDS_DIR_NAME


class ReportFile(NamedTuple):
    """The report of a day in the vault, located once: checked before the request, kept in the
    register and written by the same values."""

    vault_dir: Path
    path: Path
    # Its path in the vault, POSIX: what the register keeps and the log says.
    name: str


def locate_report_file(vault_dir: Path, day: date) -> ReportFile:
    path = find_sheets_dir(vault_dir) / f"{day.isoformat()}.md"
    return ReportFile(vault_dir, path, path.relative_to(vault_dir).as_posix())


def refuse_written_sheet(report_file: ReportFile) -> None:
    """Before the request, refuse the report already written, or a folder down to it that is a
    symbolic link; creates nothing."""
    refuse_linked_folders(report_file.vault_dir, find_sheets_dir(report_file.vault_dir))
    if has_sheet(report_file.path, report_file.vault_dir):
        raise find_sheet_exists_error(report_file)


def find_sheet_exists_error(report_file: ReportFile) -> VaultEntryRefusedError:
    return VaultEntryRefusedError(
        f"sheet_exists: {report_file.name} is there; kb trend-report never rewrites a report"
    )


def write_trend_report_sheet(
    report_file: ReportFile, response: TrendReportResponse, generated: datetime
) -> None:
    """Write the report; a report written meanwhile and seen is refused (sheet_exists), with the
    limit of post/vault_files.py."""
    content = render_trend_report_sheet(response, generated)
    vault_dir = report_file.vault_dir
    if not write_new_sheet(
        vault_dir, find_sheets_dir(vault_dir), report_file.path, content
    ):
        raise find_sheet_exists_error(report_file)


def render_trend_report_sheet(
    response: TrendReportResponse, generated: datetime
) -> str:
    """The Markdown of a report of a period of at least one window: a front matter, the period
    and what limits it, then the repositories that meet a criterion; the same response and
    instant give the same bytes."""
    period = response.period
    lines = [
        "---",
        f"generated: {format_date(generated)}",
        f"first_window: {period.windows[0].isoformat()}",
        f"last_window: {period.windows[-1].isoformat()}",
        f"windows: {len(period.windows)}",
        f"missing_windows: {len(period.missing_windows)}",
        f"windows_capped: {json.dumps(period.windows_capped)}",
        f"first_report: {json.dumps(period.first_report)}",
        f"new_evaluated: {json.dumps(period.new_evaluated)}",
        f"repositories_dropped: {response.repositories_dropped}",
        # Checked by MODEL_NAME, or null; written as JSON, which YAML reads as it is.
        f"model: {json.dumps(response.model)}",
        f"request_id: {response.request_id}",
        "---",
        "",
        f"# Tendances GitHub du {generated.date().isoformat()}",
        "",
        describe_period(period),
    ]
    for limit in describe_limits(period):
        lines += ["", limit]
    lines += [
        "",
        GH_ARCHIVE_LIMIT,
        "",
        "## Dépôts qui ressortent",
        "",
        *render_repositories(response.repositories),
        "",
        describe_missing_windows(period),
    ]
    if response.repositories_dropped:
        lines += [
            "",
            (
                f"Dépôts écartés : {response.repositories_dropped}"
                " (nom inutilisable dans un chemin)."
            ),
        ]
    return "\n".join(lines) + "\n"


def describe_period(period: TrendPeriod) -> str:
    first, last = period.windows[0].isoformat(), period.windows[-1].isoformat()
    if len(period.windows) == 1:
        return f"Période : la fenêtre du {last}, de {GH_ARCHIVE_WINDOW_DAYS} jours."
    return (
        f"Période : fenêtres du {first} au {last} ({len(period.windows)} fenêtres de"
        f" {GH_ARCHIVE_WINDOW_DAYS} jours)."
    )


def describe_limits(period: TrendPeriod) -> list[str]:
    """What the period leaves out of the criteria (docs/tendances.md, "Période")."""
    limits = []
    if period.first_report:
        limits.append("Premier compte rendu : « nouveau » n'est pas évalué.")
    elif not period.new_evaluated:
        limits.append(
            "Toutes les fenêtres du compte rendu précédent manquent : « nouveau » n'est pas"
            " évalué."
        )
    if period.windows_capped:
        limits.append(
            f"Plafond : seules les {GH_ARCHIVE_MAX_CATCH_UP_WINDOWS} fenêtres les plus récentes"
            " sont lues ; les plus anciennes depuis le compte rendu précédent sont laissées de"
            " côté."
        )
    if len(period.windows) == 1:
        limits.append(
            "Période d'une fenêtre : ni « durable » ni « en accélération » ne peuvent"
            " ressortir."
        )
    elif len(period.windows) == 2:
        limits.append(
            "Période de 2 fenêtres : « en accélération » se lit sur deux rangs."
        )
    return limits


def render_repositories(repositories: list[TrendRepository]) -> list[str]:
    if not repositories:
        return [NO_REPOSITORY]
    return [*TABLE_HEADER, *(render_row(repository) for repository in repositories)]


def render_row(repository: TrendRepository) -> str:
    """A row of the table: its URL, made from the name checked by is_repository_name, holds only
    [A-Za-z0-9_.-/] after the host, nothing a table or an autolink would read."""
    criteria = ", ".join(
        CRITERION_LABELS[criterion] for criterion in repository.criteria
    )
    trajectory = " → ".join(render_point(point) for point in repository.trajectory)
    return (
        f"| <{GITHUB_URL}{repository.repository_name}> | {criteria}"
        f" | {repository.best_rank} | {trajectory} |"
    )


def render_point(point: TrendPoint) -> str:
    if point.state == "missing":
        return MISSING
    if point.rank is None:
        return OUT_OF_TOP
    return str(point.rank)


def describe_missing_windows(period: TrendPeriod) -> str:
    if not period.missing_windows:
        return "Fenêtres manquantes : aucune."
    listed = ", ".join(window.isoformat() for window in period.missing_windows)
    return f"Fenêtres manquantes : {listed}."
