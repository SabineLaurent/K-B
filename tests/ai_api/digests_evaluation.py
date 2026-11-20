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

from digests_reference import REFERENCE_PATH, DigestsReference, read_reference
from test_digests_reference import replay_reference

from k_b.ai_api.observability.metrics import compute_fidelity_rate

# The thresholds of 15/10 (journal ADR, PR of #275, decision 7), failure thresholds for
# POST /digests by the decision of Sabine of 2026-11-08 (#482): only Sabine changes them.
SCHEMA_VALID_MIN_SHARE = 1.0
FIDELITY_MIN_RATE = 0.95
ITEMS_UNANSWERED_MAX = 0

EXIT_THRESHOLDS_MET = 0
EXIT_BELOW_THRESHOLD = 1
EXIT_USAGE = 2

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

    @property
    def schema_valid_share(self) -> float | None:
        """The calls whose last attempt is valid; None without a call."""
        return self.schema_valid_calls / self.calls if self.calls else None

    @property
    def fidelity_rate(self) -> float | None:
        """Every fact of the set weighs the same, by the formula of the metric line."""
        return compute_fidelity_rate(self.facts_found, self.facts_checked)


class Verdict(NamedTuple):
    """One row of the report."""

    measure: str
    value: str
    threshold: str
    passed: bool


def measure_replay(lines: Sequence[Mapping[str, Any]]) -> ReplayMeasures:
    """The counts of the metric lines: every call, the facts of the writings, the items the
    classification left unanswered."""
    writings = [line for line in lines if line["stage"] == "write"]
    classifications = [line for line in lines if line["stage"] == "classify"]
    return ReplayMeasures(
        calls=len(lines),
        schema_valid_calls=sum(bool(line["schema_valid"]) for line in lines),
        facts_checked=sum(line["facts_checked"] or 0 for line in writings),
        facts_found=sum(line["facts_found"] or 0 for line in writings),
        items_unanswered=sum(line["items_unanswered"] or 0 for line in classifications),
    )


def judge(measures: ReplayMeasures) -> list[Verdict]:
    """A measure that cannot be computed fails its threshold (fail closed)."""
    share = measures.schema_valid_share
    fidelity = measures.fidelity_rate
    return [
        Verdict(
            "Schémas valides après une nouvelle tentative",
            f"{format_rate(share)} ({measures.schema_valid_calls} sur {measures.calls})",
            format_rate(SCHEMA_VALID_MIN_SHARE),
            share is not None and share >= SCHEMA_VALID_MIN_SHARE,
        ),
        Verdict(
            "Fidélité (`fidelity_rate`)",
            f"{format_rate(fidelity)} ({measures.facts_found} faits sur "
            f"{measures.facts_checked})",
            f"au moins {format_rate(FIDELITY_MIN_RATE)}",
            fidelity is not None and fidelity >= FIDELITY_MIN_RATE,
        ),
        Verdict(
            "Items oubliés (`items_unanswered`)",
            str(measures.items_unanswered),
            "aucun",
            measures.items_unanswered <= ITEMS_UNANSWERED_MAX,
        ),
    ]


def format_rate(rate: float | None) -> str:
    """53,85 %, 100 %; "non mesurée" for None."""
    if rate is None:
        return "non mesurée"
    digits = f"{rate * 100:.2f}".rstrip("0").rstrip(".")
    return digits.replace(".", ",") + " %"


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


def replay_metric_lines(reference: DigestsReference) -> list[dict[str, Any]]:
    """The metric lines the AI API writes on stdout while it replays the set."""
    output = io.StringIO()
    with (
        tempfile.TemporaryDirectory() as data_dir,
        contextlib.redirect_stdout(output),
    ):
        replay_reference(reference, Path(data_dir))
    return [json.loads(line) for line in output.getvalue().splitlines()]


def evaluate(reference_path: Path, report_path: Path) -> int:
    """Replay the set, write the report, and name the exit."""
    reference = read_reference(reference_path)
    verdicts = judge(measure_replay(replay_metric_lines(reference)))
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
