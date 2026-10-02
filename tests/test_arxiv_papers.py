from datetime import UTC, datetime
from pathlib import Path

import pytest

from k_b.arxiv_papers import count_papers, read_papers, read_total_results

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_RESPONSE = (FIXTURES_DIR / "arxiv_extract.xml").read_bytes()


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
    papers = read_papers(RECORDED_RESPONSE)

    assert [paper.arxiv_id for paper in papers] == ["2609.31282", "2609.33401", "2610.01349"]
    first = papers[0]
    assert first.version == 1
    assert first.title.startswith("Resource-Optimized and Energy-Aware Agentic AI Framework")
    assert first.summary.startswith("This paper proposes a blockchain-backed agentic")
    assert first.authors == ("Toqeer Ali Syed", "Asadullah Abdullah Khan")
    assert first.published_at == datetime(2026, 9, 25, 13, 53, 50, tzinfo=UTC)
    assert first.updated_at == datetime(2026, 9, 25, 13, 53, 50, tzinfo=UTC)


def test_a_revised_paper_keeps_its_version_apart_from_its_identifier():
    revised = read_papers(RECORDED_RESPONSE)[1]

    assert revised.version == 2
    assert revised.published_at == datetime(2026, 9, 27, 9, 30, 13, tzinfo=UTC)
    assert revised.updated_at == datetime(2026, 9, 29, 16, 41, 24, tzinfo=UTC)


def test_the_url_is_the_abstract_page_without_version():
    assert read_papers(RECORDED_RESPONSE)[1].url == "https://arxiv.org/abs/2609.33401"


def test_the_total_announced_by_the_api_is_read():
    assert read_total_results(RECORDED_RESPONSE) == 3


def test_a_feed_without_entries_gives_no_paper():
    assert read_papers(feed_with_entry("")) == []


@pytest.mark.parametrize(
    "entry_id",
    [
        "https://evil.example/abs/2609.31282v1",
        "http://arxiv.org/abs/2609.31282",
    ],
)
def test_an_entry_that_is_not_an_arxiv_paper_is_rejected_and_logged(entry_id, caplog):
    assert read_papers(feed_with_entry(entry_xml(entry_id=entry_id))) == []
    assert "entry 0" in caplog.text


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
def test_an_entry_with_a_missing_or_invalid_field_is_rejected_and_logged(changes, caplog):
    assert read_papers(feed_with_entry(entry_xml(**changes))) == []
    assert "entry 0" in caplog.text


def test_a_rejected_entry_does_not_hide_the_valid_ones():
    feed = feed_with_entry(entry_xml(authors="") + entry_xml())

    assert [paper.arxiv_id for paper in read_papers(feed)] == ["2609.31282"]


def test_every_entry_is_counted_even_an_invalid_one():
    assert count_papers(RECORDED_RESPONSE) == 3
    assert count_papers(feed_with_entry(entry_xml(authors=""))) == 1


def test_a_feed_reporting_an_api_error_is_refused():
    error_entry = entry_xml(entry_id="http://arxiv.org/api/errors#incorrect_id_format_for_1234")

    with pytest.raises(ValueError, match="incorrect_id_format_for_1234"):
        count_papers(feed_with_entry(error_entry))


@pytest.mark.parametrize(
    "raw_response",
    [b"not xml", b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>', b"<html></html>"],
)
def test_a_response_that_is_not_an_arxiv_feed_is_refused(raw_response):
    with pytest.raises(ValueError):
        read_total_results(raw_response)
