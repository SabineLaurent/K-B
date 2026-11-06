import traceback
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs

import pytest

from k_b.core.quoting import quote_value
from k_b.etl.extract import collect_all_sources
from k_b.etl.raw_store import load_last_collection_dates, save_last_collection_dates
from k_b.etl.source_contract import EntryReading, PageRefusedError, list_sources
from k_b.etl.source_kinds import SOURCE_KINDS
from k_b.etl.sources.arxiv import (
    ArxivSource,
    Paper,
    convert_paper,
    count_papers,
    read_papers,
    read_total_results,
)

FIXTURES_DIR = Path(__file__).parent.parent.parent / "fixtures"
RECORDED_RESPONSE = (FIXTURES_DIR / "arxiv_extract.xml").read_bytes()
EMPTY_FEED = (
    b'<feed xmlns="http://www.w3.org/2005/Atom" '
    b'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
    b"<opensearch:totalResults>0</opensearch:totalResults></feed>"
)


@pytest.fixture
def network(fake_network):
    fake_network.body = RECORDED_RESPONSE
    return fake_network


def read_search_query(network):
    return parse_qs(network.requests[0].url.query.decode())["search_query"][0]


def test_arxiv_is_a_source_of_kb_collect():
    assert "arxiv_cscr_x_csai" in [source.name for source in list_sources(SOURCE_KINDS)]


def test_the_response_is_returned_unchanged(network):
    assert ArxivSource().fetch(last_collected_at=None) == RECORDED_RESPONSE


def test_the_request_names_k_b_and_has_a_timeout(network):
    ArxivSource().fetch(last_collected_at=None)

    request = network.requests[0]
    assert str(request.url).startswith("https://export.arxiv.org/api/query?")
    assert request.headers["User-Agent"].startswith("K-B")
    assert request.extensions["timeout"]["read"] > 0


def test_the_query_keeps_the_ai_security_papers_only(network):
    ArxivSource().fetch(last_collected_at=None)

    search_query = read_search_query(network)
    assert search_query.startswith("cat:cs.CR AND cat:cs.AI AND (abs:")
    assert 'abs:"prompt injection" OR abs:jailbreak OR' in search_query


def test_the_window_reaches_back_seven_days_before_the_last_collection(network):
    ArxivSource().fetch(last_collected_at=datetime(2026, 9, 30, 10, 5, tzinfo=UTC))

    assert "submittedDate:[202609231005 TO " in read_search_query(network)


def test_the_window_is_written_in_utc_whatever_the_stored_time_zone(network):
    paris = timezone(timedelta(hours=2))
    ArxivSource().fetch(last_collected_at=datetime(2026, 9, 30, 12, 5, tzinfo=paris))

    assert "submittedDate:[202609231005 TO " in read_search_query(network)


def test_the_collection_writes_the_arxiv_raw_under_arxiv_cscr_x_csai(network, tmp_path):
    raw_dir = tmp_path / "raw"

    collect_all_sources([ArxivSource()], raw_dir, tmp_path, COLLECTED_AT)

    raw_file_path = (
        raw_dir / "automated_watch" / "arxiv_cscr_x_csai" / "2026-10-05T093000Z.xml"
    )
    assert raw_file_path.read_bytes() == RECORDED_RESPONSE


def test_a_collection_state_keyed_arxiv_cscr_x_csai_restarts_arxiv_from_its_date(
    network, tmp_path
):
    last_collected_at = datetime(2026, 9, 30, 10, 5, tzinfo=UTC)
    save_last_collection_dates(tmp_path, {"arxiv_cscr_x_csai": last_collected_at})

    collect_all_sources([ArxivSource()], tmp_path / "raw", tmp_path, COLLECTED_AT)

    assert "submittedDate:[202609231005 TO " in read_search_query(network)
    assert load_last_collection_dates(tmp_path)["arxiv_cscr_x_csai"] == COLLECTED_AT


def test_the_window_ends_now(network):
    ArxivSource().fetch(last_collected_at=None)

    window_end = datetime.strptime(
        read_search_query(network).split(" TO ")[1][:12], "%Y%m%d%H%M"
    ).replace(tzinfo=UTC)
    assert abs(datetime.now(UTC) - window_end) < timedelta(minutes=2)


def test_a_first_collection_reaches_back_to_may_2026(network):
    ArxivSource().fetch(last_collected_at=None)

    assert "submittedDate:[202605010000 TO " in read_search_query(network)


def test_a_window_without_any_paper_returns_nothing(network):
    network.body = EMPTY_FEED

    assert ArxivSource().fetch(last_collected_at=None) is None


def test_a_page_that_does_not_hold_every_result_is_refused(network):
    network.body = RECORDED_RESPONSE.replace(
        b"<opensearch:totalResults>3<", b"<opensearch:totalResults>2001<"
    )

    with pytest.raises(PageRefusedError, match="2001"):
        ArxivSource().fetch(last_collected_at=None)


def test_a_page_with_an_invalid_entry_is_still_returned(network):
    network.body = RECORDED_RESPONSE.replace(b"<name>Lena Marsh</name>", b"")

    assert ArxivSource().fetch(last_collected_at=None) == network.body


def test_a_page_whose_entries_are_all_invalid_fails_the_collection(network):
    network.body = RECORDED_RESPONSE.replace(b"<author>", b"<contributor>").replace(
        b"</author>", b"</contributor>"
    )

    with pytest.raises(
        PageRefusedError, match="^all_items_invalid: 3 entries, all rejected"
    ):
        ArxivSource().fetch(last_collected_at=None)


def test_an_api_error_answered_with_http_200_is_refused(network):
    network.body = RECORDED_RESPONSE.replace(
        b"http://arxiv.org/abs/2609.31282v1", b"http://arxiv.org/api/errors#malformed"
    )

    with pytest.raises(PageRefusedError, match="error"):
        ArxivSource().fetch(last_collected_at=None)


COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
RAW_FILE_PATH = "automated_watch/arxiv_cscr_x_csai/2026-10-05T093000Z.xml"


def feed_with_entry(entry: str) -> bytes:
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom" '
        'xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/">'
        f"<opensearch:totalResults>1</opensearch:totalResults>{entry}</feed>"
    ).encode()


def entry_xml(
    entry_id="http://arxiv.org/abs/2609.31282v1",
    title="<title>A title</title>",
    authors="<author><name>Ada Lovelace</name></author>",
    published="<published>2026-09-25T13:53:50Z</published>",
) -> str:
    return (
        f"<entry><id>{entry_id}</id>{title}<summary>An abstract.</summary>"
        f"{published}<updated>2026-09-25T13:53:50Z</updated>{authors}</entry>"
    )


def test_a_recorded_response_gives_one_paper_per_entry():
    papers = read_papers(RECORDED_RESPONSE).entries

    assert [paper.arxiv_id for paper in papers] == [
        "2609.31282",
        "2609.33401",
        "2610.01349",
    ]
    first = papers[0]
    assert first.version == 1
    assert first.title.startswith(
        "Resource-Optimized and Energy-Aware Agentic AI Framework"
    )
    assert first.summary.startswith("This paper proposes a blockchain-backed agentic")
    assert first.authors == ("Ada May Fenwick", "Bertrand Ellis Quarrier")
    assert first.published_at == datetime(2026, 9, 25, 13, 53, 50, tzinfo=UTC)
    assert first.updated_at == datetime(2026, 9, 25, 13, 53, 50, tzinfo=UTC)


def test_a_revised_paper_keeps_its_version_apart_from_its_identifier():
    revised = read_papers(RECORDED_RESPONSE).entries[1]

    assert revised.version == 2
    assert revised.published_at == datetime(2026, 9, 27, 9, 30, 13, tzinfo=UTC)
    assert revised.updated_at == datetime(2026, 9, 29, 16, 41, 24, tzinfo=UTC)


def test_the_url_is_the_abstract_page_without_version():
    assert (
        read_papers(RECORDED_RESPONSE).entries[1].url
        == "https://arxiv.org/abs/2609.33401"
    )


def test_the_total_announced_by_the_api_is_read():
    assert read_total_results(RECORDED_RESPONSE) == 3


def test_a_feed_without_entries_gives_no_paper():
    assert read_papers(feed_with_entry("")) == EntryReading([], [])


@pytest.mark.parametrize(
    "entry_id",
    [
        "https://evil.example/abs/2609.31282v1",
        "http://arxiv.org/abs/2609.31282",
    ],
)
def test_an_entry_that_is_not_an_arxiv_paper_is_rejected_with_its_id(entry_id):
    reading = read_papers(feed_with_entry(entry_xml(entry_id=entry_id)))

    assert reading == EntryReading(
        [], [f"entry 0: id is not an arXiv paper: {entry_id!r}"]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"title": ""},
        {"title": "<title> </title>"},
        {"authors": ""},
        {"published": ""},
        {"published": "<published>2026-09-25T13:53:50</published>"},
    ],
)
def test_an_entry_with_a_missing_or_invalid_field_is_rejected_with_its_arxiv_id(
    changes,
):
    reading = read_papers(feed_with_entry(entry_xml(**changes)))

    assert reading.entries == []
    [reason] = reading.rejection_reasons
    assert reason.startswith("entry 0 ('2609.31282'): ")
    assert "Ada Lovelace" not in reason


def test_a_rejected_entry_does_not_hide_the_valid_ones():
    feed = feed_with_entry(entry_xml(authors="") + entry_xml())

    reading = read_papers(feed)

    assert [paper.arxiv_id for paper in reading.entries] == ["2609.31282"]
    assert reading.rejection_reasons == ["entry 0 ('2609.31282'): no author"]


def test_every_entry_is_counted_even_an_invalid_one():
    assert count_papers(RECORDED_RESPONSE) == 3
    assert count_papers(feed_with_entry(entry_xml(authors=""))) == 1


def test_a_feed_reporting_an_api_error_is_refused():
    error_entry = entry_xml(
        entry_id="http://arxiv.org/api/errors#incorrect_id_format_for_1234"
    )

    with pytest.raises(PageRefusedError, match="incorrect_id_format_for_1234"):
        count_papers(feed_with_entry(error_entry))


def test_the_id_of_an_api_error_is_quoted_cut():
    error_id = "http://arxiv.org/api/errors#" + "x" * 200
    error_entry = entry_xml(entry_id=error_id)

    with pytest.raises(PageRefusedError) as refusal:
        count_papers(feed_with_entry(error_entry))

    assert str(refusal.value).endswith(quote_value(error_id))
    assert error_id not in str(refusal.value)


@pytest.mark.parametrize(
    "raw_response",
    [
        b"not xml",
        b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>',
        b"<html></html>",
    ],
)
def test_a_response_that_is_not_an_arxiv_feed_is_refused(raw_response):
    with pytest.raises(PageRefusedError):
        read_total_results(raw_response)


@pytest.mark.parametrize("read_feed", [count_papers, read_total_results, read_papers])
def test_a_feed_declaring_an_internal_entity_is_refused_unexpanded(read_feed):
    raw_response = b'<!DOCTYPE feed [<!ENTITY a "x">]>' + feed_with_entry(
        entry_xml(title="<title>&a;</title>")
    )

    with pytest.raises(PageRefusedError, match="^XML refused: EntitiesForbidden$"):
        read_feed(raw_response)


def test_a_refused_entity_leaves_no_value_of_the_feed_in_the_traceback():
    raw_response = (
        b'<!DOCTYPE feed [<!ENTITY declaredname SYSTEM "https://declared.example/">]>'
        + feed_with_entry(entry_xml())
    )

    with pytest.raises(PageRefusedError) as refusal:
        read_papers(raw_response)

    trace = "".join(traceback.format_exception(refusal.value))
    assert "declaredname" not in trace
    assert "declared.example" not in trace


def test_a_feed_declaring_an_external_entity_is_refused_unread():
    raw_response = b'<!DOCTYPE feed [<!ENTITY a SYSTEM "file:///etc/hostname">]>' + (
        feed_with_entry(entry_xml(title="<title>&a;</title>"))
    )

    with pytest.raises(PageRefusedError, match="^XML refused: EntitiesForbidden$"):
        read_papers(raw_response)


def test_a_paper_keeps_its_id_without_version_and_its_revision_date():
    paper = Paper(
        arxiv_id="2509.12345",
        version=2,
        title="A paper",
        summary="What it says.",
        authors=("Ada Lovelace", "Alan Turing"),
        published_at=datetime(2025, 9, 15, 17, 0, tzinfo=UTC),
        updated_at=datetime(2025, 9, 20, 12, 0, tzinfo=UTC),
        url="https://arxiv.org/abs/2509.12345",
    )

    item = convert_paper(paper, COLLECTED_AT, RAW_FILE_PATH)

    assert item.source_code == "arxiv"
    assert item.kind == "paper"
    assert item.source_item_id == "2509.12345"
    assert item.title == "A paper"
    assert item.url == "https://arxiv.org/abs/2509.12345"
    assert item.authors == ("Ada Lovelace", "Alan Turing")
    assert item.published_at == datetime(2025, 9, 15, 17, 0, tzinfo=UTC)
    assert item.revised_at == datetime(2025, 9, 20, 12, 0, tzinfo=UTC)
    assert item.summary == "What it says."
    assert item.collected_at == COLLECTED_AT
    assert item.raw_file_path == RAW_FILE_PATH
