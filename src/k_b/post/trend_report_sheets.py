"""The trend reports in the vault: one Markdown file per day of a run, veille/tendances/<day>.md,
written once by kb trend-report from the response of the AI API, with the limit of
post/vault_files.py.

Each text is made by the code from checked values: a day, a count, a word of a closed list (a
subject of the watch among them), the name of the model, checked by MODEL_NAME, a topic, checked
by its pattern, and the name of a repository, checked by is_repository_name, which makes its URL.
The language and the license are written by neutralize_digest_text, which would break a URL
(www. escaped) in any other."""

import json
from datetime import date, datetime
from pathlib import Path
from typing import NamedTuple

from k_b.core.config import (
    GH_ARCHIVE_MAX_CATCH_UP_WINDOWS,
    GH_ARCHIVE_TOP_SIZE,
    GH_ARCHIVE_WINDOW_DAYS,
    MAX_TOPICS_FOR_SELECTION,
    TREND_DURABLE_LOOKBACK_WINDOWS,
    TREND_DURABLE_MIN_WINDOWS,
    TREND_RECENT_REPOSITORY_DAYS,
    TRENDS_DIR_NAME,
    WATCH_DIR_NAME,
)
from k_b.core.dates import format_date
from k_b.items import Caution, Criterion
from k_b.post.trend_report_client import (
    CRITERIA,
    ChoiceFailure,
    ChosenRepository,
    DroppedCandidates,
    RepositoryFacts,
    TrendPeriod,
    TrendPoint,
    TrendReportResponse,
    TrendRepository,
)
from k_b.post.vault_files import (
    VaultEntryRefusedError,
    has_sheet,
    neutralize_digest_text,
    refuse_linked_folders,
    write_new_sheet,
)

GITHUB_URL = "https://github.com/"
CRITERION_LABELS: dict[Criterion, str] = {
    "durable": "durable",
    "new": "nouveau",
    "accelerating": "en accélération",
}
# The reasons GitHub leaves a candidate out, in the order of the response.
DROP_REASON_LABELS = {
    "not_found": "introuvables",
    "unavailable_for_legal_reasons": "bloqués",
    "moved": "renommés ou déplacés",
    "id_mismatch": "remplacés",
    "forbidden": "refusés",
}
# Why the choice of the model was not made, by state of the response.
CHOICE_FAILURE_REASONS: dict[ChoiceFailure, str] = {
    "llm_timeout": "le modèle n'a pas répondu à temps",
    "llm_rate_limited": "le quota du modèle est atteint",
    "llm_unavailable": "le modèle est indisponible",
    "llm_invalid_output": "sa réponse n'a pas passé les contrôles, relance comprise",
    "llm_truncated": "sa réponse a été coupée",
    "llm_content_filtered": "le filtre de contenu d'Azure a refusé la demande",
}
NO_CANDIDATE_READ = "aucun candidat lu"
OUT_OF_TOP = "hors top"
MISSING = "—"
# The limit of the counts (docs/tendances.md, "Limite de GH Archive"): never stars gained alone.
GH_ARCHIVE_LIMIT = (
    "Les rangs viennent de GH Archive, un échantillon d'environ 1 % des étoiles données sur"
    " GitHub (mesure du 2026-10-29) : des rangs proches ne se départagent pas. Les dates de"
    " création et les étoiles totales sont lues sur GitHub."
)
NO_REPOSITORY = "Aucun dépôt ne remplit un critère sur la période."
# The table shows the period alone: without this, a repository in one window of it looks
# wrongly durable.
DURABLE_READING = (
    f"« durable » : dans le top {GH_ARCHIVE_TOP_SIZE} de {TREND_DURABLE_MIN_WINDOWS} fenêtres sans"
    f" jour commun, lues sur la période et les {TREND_DURABLE_LOOKBACK_WINDOWS} fenêtres qui la"
    " précèdent (non affichées dans le tableau)."
)
TABLE_HEADER = (
    (
        "| Dépôt | Critères | Meilleur rang | Trajectoire (rang par fenêtre) | Créé le"
        " | Étoiles totales | Prudence |"
    ),
    "|---|---|---|---|---|---|---|",
)
CAUTION_LABELS: dict[Caution, str] = {
    "created_recently": f"créé il y a moins de {TREND_RECENT_REPOSITORY_DAYS} jours",
    # Not "no license": GitHub also says none for a license it does not recognize.
    "no_license": "aucune licence reconnue par GitHub",
}


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
        # A state of a closed list, or null.
        f"choice_failure: {json.dumps(response.choice_failure)}",
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
        "## Choisis par le modèle",
        "",
        *render_choice(response),
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
    if response.candidates.read < response.candidates.selected:
        lines += ["", describe_dropped_candidates(response.candidates.dropped)]
    return "\n".join(lines) + "\n"


def render_choice(response: TrendReportResponse) -> list[str]:
    """The repositories the model chose, in its order, or why it chose none."""
    read = response.candidates.read
    if response.model is None:
        reason = (
            NO_CANDIDATE_READ
            if response.choice_failure is None
            else CHOICE_FAILURE_REASONS[response.choice_failure]
        )
        return [f"Choix non fait : {reason}."]
    candidates = f"{read} candidat{'s' if read > 1 else ''}"
    if not response.chosen:
        return [f"{response.model} n'en a retenu aucun sur {candidates}."]
    return [
        f"{response.model} en a retenu {len(response.chosen)} sur {candidates} :",
        "",
        *(
            line
            for chosen in response.chosen
            for line in (render_chosen(chosen), render_facts(chosen.facts))
        ),
    ]


def render_chosen(chosen: ChosenRepository) -> str:
    """Its URL, made as in render_row, then its criteria of the code and its subjects."""
    parts = []
    criteria = [CRITERION_LABELS[c] for c in CRITERIA if c in chosen.criteria]
    if criteria:
        parts.append(", ".join(criteria))
    if chosen.watch_subjects:
        parts.append(f"sujet de la veille ({', '.join(chosen.watch_subjects)})")
    return f"- <{GITHUB_URL}{chosen.repository_name}> : {' ; '.join(parts)}"


def render_facts(facts: RepositoryFacts) -> str:
    """The line under a repository chosen, indented to stay in its item; a fact GitHub does not
    give is left out, a license it does not recognize said by its caution."""
    stars = facts.stars_total
    parts = [f"Créé le {format_created_day(facts)}"]
    language = neutralize_digest_text(facts.language or "")
    if language:
        parts.append(language)
    if facts.license:
        parts.append(neutralize_digest_text(facts.license))
    parts.append(f"{stars} étoile{'s' if stars > 1 else ''}")
    if facts.topics:
        parts.append(", ".join(facts.topics[:MAX_TOPICS_FOR_SELECTION]))
    if facts.cautions:
        parts.append(f"Prudence : {describe_cautions(facts)}")
    return f"  {' ; '.join(parts)}"


def format_created_day(facts: RepositoryFacts) -> str:
    return facts.created_at.date().isoformat()


def describe_cautions(facts: RepositoryFacts) -> str:
    return ", ".join(CAUTION_LABELS[caution] for caution in facts.cautions)


def describe_dropped_candidates(dropped: DroppedCandidates) -> str:
    """The candidates GitHub left out, by reason, the reasons at 0 left out."""
    counts = dropped.model_dump()
    reasons = ", ".join(
        f"{label} : {counts[reason]}"
        for reason, label in DROP_REASON_LABELS.items()
        if counts[reason]
    )
    return f"Candidats écartés par GitHub : {sum(counts.values())} ({reasons})."


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
    lines = [*TABLE_HEADER, *(render_row(repository) for repository in repositories)]
    if any("durable" in repository.criteria for repository in repositories):
        lines += ["", DURABLE_READING]
    return lines


def render_row(repository: TrendRepository) -> str:
    """A row of the table: its URL, made from the name checked by is_repository_name, holds only
    [A-Za-z0-9_.-/] after the host, nothing a table or an autolink would read."""
    criteria = ", ".join(
        CRITERION_LABELS[criterion] for criterion in repository.criteria
    )
    trajectory = " → ".join(render_point(point) for point in repository.trajectory)
    return (
        f"| <{GITHUB_URL}{repository.repository_name}> | {criteria}"
        f" | {repository.best_rank} | {trajectory} | {render_row_facts(repository.facts)} |"
    )


def render_row_facts(facts: RepositoryFacts | None) -> str:
    """A date, a count and words of a closed list: nothing a table would read."""
    if facts is None:
        return f"{MISSING} | {MISSING} | {MISSING}"
    return (
        f"{format_created_day(facts)} | {facts.stars_total}"
        f" | {describe_cautions(facts) or MISSING}"
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
