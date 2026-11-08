"""The reference set of POST /digests (#479): outputs of a real model, recorded once by
digests_reference.py, replayed through the route on the items of the extracts they were recorded
on."""

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


def read_license_rows():
    """The rows of the table "Contenus de tiers" of the README, by the file they name."""
    return {
        line.split("|")[1].strip(" `"): line
        for line in README_PATH.read_text().splitlines()
        if line.startswith("| `tests/")
    }


def test_each_recorded_output_replays_through_post_digests(tmp_path):
    reference = read_reference(REFERENCE_PATH)
    license_rows = read_license_rows()
    assert reference.calls
    assert all(call.model != REPLAY_MODEL for call in reference.calls)
    assert all(
        item.license in license_rows[item.source_file] for item in reference.items
    )
    steps = [call.step for call in reference.calls]
    transport = ReplayTransport(steps)
    with open_data_api(build_reference_base(tmp_path)) as data_api:
        assert (
            read_reference_items(
                data_api, reference.request_time, reference.window_days
            )
            == reference.items
        )
        ai_api = build_ai_api(
            replay_settings(steps),
            reference.subjects,
            reference.request_time,
            data_api,
            transport,
        )
        response = post_digests(ai_api, reference.window_days)
    assert response.status_code == 200
    assert [read_stage(request) for request in transport.requests] == [
        call.stage for call in reference.calls
    ]
