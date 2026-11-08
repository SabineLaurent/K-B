"""The reference set of POST /digests replays through the route, on the items it was recorded on."""

import json

from digests_reference import (
    README_PATH,
    REFERENCE_PATH,
    build_ai_api,
    build_reference_base,
    open_data_api,
    post_digests,
    read_reference,
    read_reference_items,
    read_stage,
    replay_settings,
)

from k_b.ai_api.connectors.llm_replay import ReplayTransport
from k_b.ai_api.connectors.llm_settings import REPLAY_MODEL


def read_licenses():
    """The column "Licence" of the table "Contenus de tiers" of the README, by the file named."""
    rows = [
        line.split("|")
        for line in README_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("| `tests/")
    ]
    return {cells[1].strip(" `"): cells[3] for cells in rows}


def replay_reference(reference, data_dir):
    """The answer of POST /digests on the items of the set, its model replaying the set, and the
    requests the model was sent."""
    steps = [call.step for call in reference.calls]
    transport = ReplayTransport(steps)
    with open_data_api(build_reference_base(data_dir)) as data_api:
        items = read_reference_items(
            data_api, reference.request_time, reference.window_days
        )
        assert items == reference.items
        ai_api = build_ai_api(
            replay_settings(steps),
            reference.subjects,
            reference.request_time,
            data_api,
            transport,
        )
        response = post_digests(ai_api, reference.window_days)
    return response, transport.requests


def test_each_recorded_output_replays_through_post_digests(tmp_path):
    reference = read_reference(REFERENCE_PATH)
    licenses = read_licenses()
    assert reference.calls
    assert all(call.model != REPLAY_MODEL for call in reference.calls)
    assert all(item.license in licenses[item.source_file] for item in reference.items)

    response, requests = replay_reference(reference, tmp_path)

    assert response.status_code == 200
    # Each writing of the set answered at its first attempt: one digest each.
    assert response.json()["failed_subjects"] == []
    assert len(response.json()["digests"]) == sum(
        call.stage == "write" for call in reference.calls
    )
    assert [read_stage(request) for request in requests] == [
        call.stage for call in reference.calls
    ]


def test_the_facts_of_the_set_are_all_in_their_item_not_all_in_their_text(
    tmp_path, capsys
):
    """No fact of the set is missing from its item; 12 of its 26 are missing from the text of
    their claim."""
    replay_reference(read_reference(REFERENCE_PATH), tmp_path)

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    writes = [line for line in lines if line["stage"] == "write"]
    assert [
        sum(line[field] for line in writes)
        for field in (
            "facts_checked",
            "facts_found_in_item",
            "facts_found_in_text",
            "facts_found",
        )
    ] == [26, 26, 14, 14]
