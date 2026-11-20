"""Replay the reference set of POST /digests and judge it against the thresholds of 15/10 (#482).

The job digests-reference of ci.yml runs it:
    uv run python tests/ai_api/digests_evaluation.py <report.md>
It writes the report, then exits with EXIT_BELOW_THRESHOLD if one threshold is not met. The set is
replayed, never sent to the model: the evaluation tests the checks of K-B on recorded outputs.
"""

import contextlib
import io
import json
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from digests_reference import (
    REFERENCE_PATH,
    DigestsReference,
    read_reference,
    read_stage,
)
from test_digests_reference import replay_reference

from k_b.ai_api.observability.metrics import LLM_CALL_EVENT

# The thresholds of 15/10 (journal ADR, PR of #275, decision 7), failure thresholds for
# POST /digests by the decision of Sabine of 2026-11-08 (#482): only Sabine changes them. In
# percent, compared on the counts: a rate rounded never crosses a threshold.
SCHEMA_VALID_MIN_PERCENT = 100
FIDELITY_MIN_PERCENT = 95
ITEMS_UNANSWERED_MAX = 0
REPLAY_STATUS = 200

EXIT_THRESHOLDS_MET = 0
EXIT_BELOW_THRESHOLD = 1
EXIT_USAGE = 2

HUNDREDTHS_OF_PERCENT = 10_000
REPORT_HEADER = (
    "| Mesure | Valeur | Seuil | Résultat |",
    "|---|---|---|---|",
)


class ReplayMeasures(NamedTuple):
    """The counts of the metric lines of one replay of the set."""

    calls: int
    schema_valid_calls: int
    facts_checked: int
    facts_found: int
    items_unanswered: int


class Verdict(NamedTuple):
    """One row of the report."""

    measure: str
    value: str
    threshold: str
    passed: bool


def measure_replay(lines: Sequence[Mapping[str, Any]]) -> ReplayMeasures:
    """The counts of the metric lines of the calls: every call, the facts of the writings, the
    items the classification left unanswered."""
    calls = [line for line in lines if line.get("event") == LLM_CALL_EVENT]
    writings = [line for line in calls if line["stage"] == "write"]
    classifications = [line for line in calls if line["stage"] == "classify"]
    return ReplayMeasures(
        calls=len(calls),
        schema_valid_calls=sum(bool(line["schema_valid"]) for line in calls),
        facts_checked=sum(line["facts_checked"] or 0 for line in writings),
        facts_found=sum(line["facts_found"] or 0 for line in writings),
        items_unanswered=sum(line["items_unanswered"] or 0 for line in classifications),
    )


def judge_replay(
    recorded_stages: Sequence[str], sent_stages: Sequence[str], status: int
) -> Verdict:
    """The replay sent the calls of the set, in their order, and the route answered 200: else the
    measures are not those of the set (fail closed)."""
    return Verdict(
        "Appels rejoués",
        f"{len(sent_stages)} sur {len(recorded_stages)} enregistrés, réponse {status}",
        f"tous, dans l'ordre, réponse {REPLAY_STATUS}",
        list(sent_stages) == list(recorded_stages) and status == REPLAY_STATUS,
    )


def judge(measures: ReplayMeasures) -> list[Verdict]:
    """A measure that cannot be computed fails its threshold (fail closed)."""
    return [
        Verdict(
            "Schémas valides après une nouvelle tentative",
            f"{format_share(measures.schema_valid_calls, measures.calls)} "
            f"({measures.schema_valid_calls} sur {measures.calls})",
            format_share(SCHEMA_VALID_MIN_PERCENT, 100),
            is_at_least(
                measures.schema_valid_calls, measures.calls, SCHEMA_VALID_MIN_PERCENT
            ),
        ),
        Verdict(
            "Fidélité (`fidelity_rate`)",
            f"{format_share(measures.facts_found, measures.facts_checked)} "
            f"({measures.facts_found} faits sur {measures.facts_checked})",
            f"au moins {format_share(FIDELITY_MIN_PERCENT, 100)}",
            is_at_least(
                measures.facts_found, measures.facts_checked, FIDELITY_MIN_PERCENT
            ),
        ),
        Verdict(
            "Items oubliés (`items_unanswered`)",
            str(measures.items_unanswered),
            "aucun",
            measures.items_unanswered <= ITEMS_UNANSWERED_MAX,
        ),
    ]


def is_at_least(part: int, whole: int, minimum_percent: int) -> bool:
    """In integers: part / whole >= minimum_percent %, never with nothing to count."""
    return whole > 0 and part * 100 >= minimum_percent * whole


def format_share(part: int, whole: int) -> str:
    """53,84 %, 100 %: truncated to the hundredth, never rounded up to a threshold; "non
    mesurée" with nothing to count."""
    if whole == 0:
        return "non mesurée"
    units, hundredths = divmod(part * HUNDREDTHS_OF_PERCENT // whole, 100)
    if hundredths == 0:
        return f"{units} %"
    return f"{units},{hundredths:02d}".rstrip("0") + " %"


def format_report(verdicts: Sequence[Verdict]) -> str:
    """The table of the report: one row per measure."""
    rows = [
        f"| {verdict.measure} | {verdict.value} | {verdict.threshold} | "
        f"{'tenu' if verdict.passed else 'non tenu'} |"
        for verdict in verdicts
    ]
    return "\n".join([*REPORT_HEADER, *rows]) + "\n"


def describe_set(reference: DigestsReference) -> str:
    """The models and prompts the set was recorded with: names only, never a text of an item."""
    models = sorted({call.model for call in reference.calls})
    prompts = sorted({call.prompt_version for call in reference.calls})
    return (
        "# Jeu de référence de POST /digests, contre les seuils du 15/10\n\n"
        f"Modèle : {', '.join(models)} ; consignes : {', '.join(prompts)} ; "
        f"{len(reference.items)} items, {len(reference.calls)} appels.\n\n"
    )


def replay_set(reference: DigestsReference) -> list[Verdict]:
    """Replay the set and judge the replay, then its metric lines (written on stdout)."""
    output = io.StringIO()
    with (
        tempfile.TemporaryDirectory() as data_dir,
        contextlib.redirect_stdout(output),
    ):
        response, requests = replay_reference(reference, Path(data_dir))
    lines = [json.loads(line) for line in output.getvalue().splitlines()]
    return [
        judge_replay(
            [call.stage for call in reference.calls],
            [read_stage(request) for request in requests],
            response.status_code,
        ),
        *judge(measure_replay(lines)),
    ]


def evaluate(reference_path: Path, report_path: Path) -> int:
    """Replay the set, write the report, and name the exit."""
    reference = read_reference(reference_path)
    verdicts = replay_set(reference)
    report = describe_set(reference) + format_report(verdicts)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(report)
    if all(verdict.passed for verdict in verdicts):
        return EXIT_THRESHOLDS_MET
    return EXIT_BELOW_THRESHOLD


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: digests_evaluation.py <report.md>", file=sys.stderr)
        sys.exit(EXIT_USAGE)
    sys.exit(evaluate(REFERENCE_PATH, Path(sys.argv[1])))
