"""GET /items on the test base (tests/fixtures/items_database.sql): its ids are the ones the
tests name."""

import pytest

from k_b.data_api.routers import item_router
from k_b.database.reading import ItemPage

# The fields of an item of the list (docs/specs-api.md, "Réponse"): nothing else is served.
LISTED_FIELDS = {"id", "kind", "title", "source_date", "url", "withdrawn_at"}


def test_each_kind_is_listed_with_the_fields_of_the_spec(client, authorization):
    response = client.get("/items", params={"limit": 100}, headers=authorization)

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["kind"] for item in items} == {
        "paper",
        "vulnerability",
        "release",
        "advisory",
        "newsletter_article",
        "zotero_entry",
    }
    paper = next(item for item in items if item["id"] == 1)
    assert paper == {
        "id": 1,
        "kind": "paper",
        "title": "Resource-Optimized and Energy-Aware Agentic AI Framework Anchored on Blockchain for Secure Software Supply Chains",
        "source_date": "2026-09-25T13:53:50Z",
        "url": "https://arxiv.org/abs/2609.31282",
        "withdrawn_at": None,
    }


@pytest.mark.parametrize(
    ("params", "expected_ids"),
    [
        ({"kind": ["paper", "advisory"]}, [2, 1, 9, 10, 17]),
        ({"since": "2026-10-07T00:00:00+02:00"}, [12, 11]),
        ({"q": "blockchain"}, [1]),
        ({"limit": 2}, [12, 11]),
        ({"limit": 2, "offset": 2}, [13, 15]),
    ],
)
def test_kind_since_q_limit_offset_filter_as_the_reading(
    client, authorization, params, expected_ids
):
    response = client.get("/items", params=params, headers=authorization)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == expected_ids


@pytest.mark.parametrize(
    ("query", "parameter"),
    [
        ("limit=0", "limit"),
        ("limit=101", "limit"),
        ("offset=-1", "offset"),
        ("offset=10001", "offset"),
        ("q=", "q"),
        ("q=" + "a" * 201, "q"),
        ("q=a%00b", "q"),
        ("kind=vuln", "kind"),
        ("since=2026-10-07T00:00:00", "since"),
        ("since=0001-01-01T00:00:00%2B01:00", "since"),
        ("since=9999-12-31T23:59:59.5Z", "since"),
        # A number is not read as a Unix time: since is an ISO 8601 date with its zone.
        ("since=20261007", "since"),
        ("since=0", "since"),
        ("since=1700000000", "since"),
    ],
)
def test_a_parameter_out_of_bounds_gives_422_with_its_name_only(
    client, authorization, query, parameter
):
    response = client.get(f"/items?{query}", headers=authorization)

    assert response.status_code == 422
    assert response.json() == {"error": "invalid_parameter", "parameters": [parameter]}


@pytest.mark.parametrize(
    ("offset", "limit", "read_next_offset", "expected_next_offset"),
    [(9980, 20, 10_000, 10_000), (10_000, 100, 10_100, None), (0, 20, None, None)],
)
def test_next_offset_stops_at_the_offset_bound(
    client,
    authorization,
    monkeypatch,
    offset,
    limit,
    read_next_offset,
    expected_next_offset,
):
    # A base of 10 000 items is not written for it: the reading gives the next offset.
    monkeypatch.setattr(
        item_router, "read_items", lambda *_, **__: ItemPage([], read_next_offset)
    )

    response = client.get(
        "/items", params={"offset": offset, "limit": limit}, headers=authorization
    )

    assert response.status_code == 200
    assert response.json() == {"items": [], "next_offset": expected_next_offset}


def test_the_list_serves_only_the_six_fields(client, authorization):
    """API3: a whitelist of six fields. The Zotero entry 14 has highlights, the paper 1 an author
    and a summary, every item a raw file path and a date of collection: none is served."""
    response = client.get("/items", params={"limit": 100}, headers=authorization)

    items = response.json()["items"]
    assert 14 in {item["id"] for item in items}
    assert all(set(item) == LISTED_FIELDS for item in items)
    for absent in (
        "A highlighted sentence on the first page.",
        "A comment on it.",
        "Toqeer Ali Syed",
        "This paper proposes",
        "raw_file_path",
        "selected_library/zotero/",
        "automated_watch/",
        "collected_at",
    ):
        assert absent not in response.text


def test_post_items_gives_405(client, authorization):
    response = client.post("/items", headers=authorization)

    assert response.status_code == 405
    assert response.json() == {"error": "method_not_allowed"}
