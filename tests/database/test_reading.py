"""The reading of the items and of the highlights (#183), on the test base of
tests/fixtures/items_database.sql: its ids are the ones the tests name."""

import typing
from datetime import UTC, datetime, timedelta, timezone

import pytest

from k_b.database.connection import connect_database_read_only
from k_b.database.reading import (
    ListedItem,
    StoredHighlight,
    read_highlights,
    read_items,
)
from k_b.items import ItemKind

# Every item of the test base, in the order of the reading: source_date, then id, descending.
ALL_IDS = [12, 11, 13, 15, 6, 14, 7, 8, 3, 2, 4, 1, 16, 9, 10, 5]
PLUS_TWO_HOURS = timezone(timedelta(hours=2))


@pytest.fixture
def connection(items_database):
    connection = connect_database_read_only(items_database)
    yield connection
    connection.close()


def read_ids(connection, **filters):
    return [item.id for item in read_items(connection, limit=100, **filters).items]


def read_item(connection, item_id):
    return next(
        item for item in read_items(connection, limit=100).items if item.id == item_id
    )


@pytest.mark.parametrize(
    "listed_item",
    [
        ListedItem(
            1,
            "paper",
            "Resource-Optimized and Energy-Aware Agentic AI Framework Anchored on Blockchain"
            " for Secure Software Supply Chains",
            "2026-09-25T13:53:50Z",
            "https://arxiv.org/abs/2609.31282",
            None,
        ),
        ListedItem(
            3,
            "vulnerability",
            "Apple Multiple Products Out-of-Bounds Write Vulnerability",
            "2026-09-29T00:00:00Z",
            "https://nvd.nist.gov/vuln/detail/CVE-2026-86950",
            None,
        ),
        ListedItem(
            6,
            "release",
            "anthropics/claude-code Claude Code 2.1.287",
            "2026-10-01T18:00:22Z",
            "https://github.com/anthropics/claude-code/releases/tag/v2.1.287",
            None,
        ),
        ListedItem(
            9,
            "advisory",
            "LangGraph Checkpoint: Unsafe JSON deserialization in checkpoint loading",
            "2026-06-25T18:25:42Z",
            "https://github.com/advisories/GHSA-fjqc-hq36-qh5p",
            None,
        ),
        ListedItem(
            11,
            "newsletter_article",
            "Mistral Large 4 (9 minute read)",
            "2026-10-07T00:00:00Z",
            "https://mistral.ai/news/mistral-large-4/",
            None,
        ),
        ListedItem(
            14,
            "zotero_entry",
            "Prompt injection through tool results",
            "2026-10-01T08:15:00Z",
            "http://arxiv.org/abs/2609.00001",
            None,
        ),
        ListedItem(
            16,
            "zotero_entry",
            "A web page in the trash",
            "2026-09-20T10:00:00Z",
            None,
            None,
        ),
    ],
    ids=lambda listed_item: f"{listed_item.kind}-{listed_item.id}",
)
def test_an_item_of_each_kind_has_its_title_url_and_date(connection, listed_item):
    assert read_item(connection, listed_item.id) == listed_item


@pytest.mark.parametrize(
    ("item_id", "title"),
    [(7, "anthropics/claude-code v2.1.286"), (8, "anthropics/claude-code v2.1.285")],
    ids=["no-name", "empty-name"],
)
def test_a_release_without_a_name_is_titled_by_its_tag(connection, item_id, title):
    assert read_item(connection, item_id).title == title


@pytest.mark.parametrize("kind", typing.get_args(ItemKind))
def test_each_kind_has_its_branch(connection, kind):
    kinds_read = {
        item.kind for item in read_items(connection, limit=100, kinds=[kind]).items
    }

    assert kinds_read == {kind}


def test_without_a_kind_every_kind_is_read(connection):
    kinds_read = {item.kind for item in read_items(connection, limit=100).items}

    assert kinds_read == set(typing.get_args(ItemKind))


def test_a_kind_is_matched_exactly_and_may_be_repeated(connection):
    vulnerabilities = read_items(connection, limit=100, kinds=["vulnerability"]).items
    papers_and_releases = read_items(
        connection, limit=100, kinds=["paper", "release"]
    ).items

    assert {item.kind for item in vulnerabilities} == {"vulnerability"}
    assert {item.kind for item in papers_and_releases} == {"paper", "release"}


def test_since_is_converted_to_utc_before_the_comparison(connection):
    # 2026-10-01T20:00:22+02:00 is the moment of the release 6, 2026-10-01T18:00:22Z: read as
    # written, without its time zone, it would come after it.
    since = datetime(2026, 10, 1, 20, 0, 22, tzinfo=PLUS_TWO_HOURS)

    assert 6 in read_ids(connection, kinds=["release"], since=since)


def test_since_takes_the_day_of_its_time_zone(connection):
    # The example of docs/specs-api.md: 2026-10-07T00:00:00+02:00 takes the edition of
    # 2026-10-07, written at midnight UTC, and not an earlier one.
    since = datetime(2026, 10, 7, tzinfo=PLUS_TWO_HOURS)

    assert read_ids(connection, kinds=["newsletter_article"], since=since) == [12, 11]


def test_since_within_a_second_leaves_out_the_item_of_that_second(connection):
    item_second = datetime(2026, 10, 1, 18, 0, 22, tzinfo=UTC)

    assert 6 in read_ids(connection, since=item_second)
    assert 6 not in read_ids(
        connection, since=item_second + timedelta(milliseconds=500)
    )


@pytest.mark.parametrize(
    "since",
    [
        datetime(2026, 10, 7),
        datetime(9999, 12, 31, 23, 59, 59, 500_000, tzinfo=UTC),
        datetime(1, 1, 1, tzinfo=PLUS_TWO_HOURS),
    ],
    ids=["naive", "beyond-the-last-second", "before-the-first-day-in-utc"],
)
def test_a_since_without_time_zone_or_out_of_range_is_refused(connection, since):
    with pytest.raises(ValueError, match="since"):
        read_items(connection, limit=100, since=since)


@pytest.mark.parametrize("search_text", ["v2%286", "v2_1"])
def test_a_percent_or_an_underscore_is_searched_as_written(connection, search_text):
    # As wildcards, they would find the releases titled v2.1.286 and v2.1.285.
    assert read_ids(connection, search_text=search_text) == []


def test_an_underscore_finds_the_text_that_holds_it(connection):
    assert read_ids(connection, search_text="CODE_DISABLE") == [8]


def test_a_backslash_is_searched_as_written(connection):
    assert read_ids(connection, search_text="\\") == []


def test_an_empty_search_is_refused(connection):
    with pytest.raises(ValueError, match="search_text"):
        read_items(connection, limit=100, search_text="")


def test_the_search_reads_the_title_and_the_summary(connection):
    # The title of a release begins with its repository; lifecycle is in a summary only.
    assert read_ids(connection, search_text="claude-code") == [6, 7, 8]
    assert read_ids(connection, search_text="LIFECYCLE") == [1]


def test_the_mode_follows_the_source_of_the_item(connection):
    assert read_ids(connection, mode="library") == [15, 14, 16]
    assert {
        item.kind for item in read_items(connection, limit=100, mode="watch").items
    } == set(typing.get_args(ItemKind)) - {"zotero_entry"}


def test_the_items_are_sorted_by_date_then_by_id_descending(connection):
    assert read_ids(connection) == ALL_IDS


def test_a_page_gives_the_offset_of_the_next_one(connection):
    first_page = read_items(connection, limit=2)
    second_page = read_items(connection, limit=2, offset=2)

    assert [item.id for item in first_page.items] == ALL_IDS[:2]
    assert first_page.next_offset == 2
    assert [item.id for item in second_page.items] == ALL_IDS[2:4]
    assert second_page.next_offset == 4


def test_the_last_page_has_no_next_offset(connection):
    # Exactly limit items remain: no next page.
    last_page = read_items(connection, limit=4, offset=len(ALL_IDS) - 4)

    assert [item.id for item in last_page.items] == ALL_IDS[-4:]
    assert last_page.next_offset is None


@pytest.mark.parametrize(
    ("limit", "offset"), [(0, 0), (-1, 0), (1, -1)], ids=["zero", "negative", "offset"]
)
def test_a_limit_below_one_or_a_negative_offset_is_refused(connection, limit, offset):
    with pytest.raises(ValueError, match="limit|offset"):
        read_items(connection, limit=limit, offset=offset)


def test_the_withdrawn_rows_are_listed_with_their_date(connection):
    assert read_item(connection, 5).withdrawn_at == "2026-10-06T09:30:00Z"
    assert read_item(connection, 15).withdrawn_at == "2026-10-06T09:30:00Z"


def test_the_highlights_of_an_entry_withdrawn_ones_included(connection):
    assert read_highlights(connection, 14) == [
        StoredHighlight(
            "ANNOTAA2",
            "A highlighted sentence on the first page.",
            "A comment on it.",
            "2026-10-05T08:42:30Z",
            None,
            None,
        ),
        StoredHighlight(
            "ANNOTAA1",
            "A highlighted sentence on the third page.",
            None,
            "2026-10-05T08:50:00Z",
            None,
            None,
        ),
        StoredHighlight(
            "ANNOTAA4",
            "A highlight in the trash.",
            None,
            "2026-10-05T08:56:00Z",
            None,
            "2026-10-06T09:30:00Z",
        ),
    ]


def test_an_entry_without_highlight_has_none(connection):
    assert read_highlights(connection, 15) == []
