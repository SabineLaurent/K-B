"""The evaluation of the reference set fails under each threshold of 15/10, and writes its report."""

import json

import pytest
from digests_evaluation import (
    EXIT_BELOW_THRESHOLD,
    evaluate,
    format_report,
    judge,
    measure_replay,
)
from digests_reference import REFERENCE_PATH

from k_b.ai_api.observability.metrics import compute_fidelity_rate

OUTPUT_OUT_OF_SCHEMA = json.dumps({"claims": "not a list"})


def classification_line(*, schema_valid=True, items_unanswered=0):
    return {
        "stage": "classify",
        "schema_valid": schema_valid,
        "items_unanswered": items_unanswered,
        "facts_checked": None,
        "facts_found": None,
    }


def writing_line(*, schema_valid=True, facts_checked=20, facts_found=20):
    return {
        "stage": "write",
        "schema_valid": schema_valid,
        "items_unanswered": 0,
        "facts_checked": facts_checked,
        "facts_found": facts_found,
    }


def is_passed(lines):
    return all(verdict.passed for verdict in judge(measure_replay(lines)))


def test_a_replay_at_each_limit_meets_the_thresholds():
    """19 facts found of 20 is 95 %: the limit holds."""
    lines = [classification_line(), writing_line(facts_found=19)]

    assert is_passed(lines)


@pytest.mark.parametrize(
    "lines",
    [
        pytest.param(
            [classification_line(), writing_line(facts_found=18)], id="fidelity_90"
        ),
        pytest.param(
            [classification_line(), writing_line(schema_valid=False)],
            id="one_schema_invalid",
        ),
        pytest.param(
            [classification_line(items_unanswered=1), writing_line()],
            id="one_item_forgotten",
        ),
        pytest.param(
            [classification_line(), writing_line(facts_checked=0, facts_found=0)],
            id="no_fact_checked",
        ),
        pytest.param([], id="no_call"),
    ],
)
def test_a_replay_under_one_threshold_fails(lines):
    assert not is_passed(lines)


def test_the_fidelity_weighs_each_fact_of_the_set_the_same():
    """2 of 2 facts and 17 of 20: 19 of 22, under 95 %, where the mean of the two rates is 92.5 %."""
    lines = [
        classification_line(),
        writing_line(facts_checked=2, facts_found=2),
        writing_line(facts_checked=20, facts_found=17),
    ]

    assert measure_replay(lines).fidelity_rate == compute_fidelity_rate(19, 22)


def test_the_report_gives_each_measure_its_value_its_threshold_and_its_result():
    lines = [classification_line(), writing_line(facts_checked=26, facts_found=14)]

    report = format_report(judge(measure_replay(lines)))

    assert (
        "| Schémas valides après une nouvelle tentative | 100 % (2 sur 2) | 100 % | tenu |"
        in report
    )
    assert (
        "| Fidélité (`fidelity_rate`) | 53,85 % (14 faits sur 26) | au moins 95 % | non tenu |"
        in report
    )
    assert "| Items oubliés (`items_unanswered`) | 0 | aucun | tenu |" in report


def degrade_first_writing(reference_path, degraded_path):
    """A copy of the set where the first writing answers out of schema, at its attempt and at its
    new attempt."""
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    calls = reference["calls"]
    first = next(index for index, call in enumerate(calls) if call["stage"] == "write")
    body = json.loads(calls[first]["step"]["body"])
    body["choices"][0]["message"]["content"] = OUTPUT_OUT_OF_SCHEMA
    calls[first]["step"]["body"] = json.dumps(body)
    calls.insert(first + 1, calls[first])
    degraded_path.write_text(json.dumps(reference), encoding="utf-8")


def test_a_degraded_set_fails_the_evaluation_and_its_report_says_which_threshold(
    tmp_path,
):
    degraded_path = tmp_path / "degraded.json"
    report_path = tmp_path / "reports" / "report.md"
    degrade_first_writing(REFERENCE_PATH, degraded_path)

    exit_code = evaluate(degraded_path, report_path)

    assert exit_code == EXIT_BELOW_THRESHOLD
    schema_row = next(
        line
        for line in report_path.read_text(encoding="utf-8").splitlines()
        if line.startswith("| Schémas valides")
    )
    assert schema_row.endswith("| non tenu |")
