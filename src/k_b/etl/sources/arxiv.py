"""The arXiv source: its download (E), then its reader (T).

Download the AI security papers submitted to arXiv, as the API returns them.

Read the papers of a raw arXiv API response (an Atom feed), and convert each one into an item.
"""

import logging
import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from k_b.etl.http_download import download
from k_b.etl.raw_store import AUTOMATED_WATCH_DIR_NAME
from k_b.etl.source_contract import SourceReader
from k_b.items import ARXIV_ID, Item, SourceCode, parse_aware_datetime

logger = logging.getLogger(__name__)

# The source of its items, in the source table of the base.
SOURCE_CODE: SourceCode = "arxiv"
API_URL = "https://export.arxiv.org/api/query"
# A page of 35 papers weighs 93 KB in 2026, about 2.7 KB a paper: 2,000 papers weigh 5.3 MB.
MAX_RESPONSE_BYTES = 6 * 1024 * 1024
# The API maximum. About 40 papers per window: one page holds them all.
PAPERS_PER_PAGE = 2000
# Papers both in cs.CR and cs.AI whose abstract has one of these keywords (decided in #6).
KEYWORDS = [
    "prompt injection",
    "jailbreak",
    "red teaming",
    "adversarial attack",
    "backdoor",
    "poisoning",
    "membership inference",
    "agent security",
]
# A paper is searchable only once announced, up to 3.5 days after its submission (Thursday
# 14:00 to Sunday 20:00, New York time), later on holidays. The window reaches back this far
# before the last collection so that late announcements are not lost; the overlap with the
# previous raw file is removed when merging, by arXiv identifier.
ANNOUNCEMENT_DELAY_MARGIN = timedelta(days=7)
# The first collection reaches back to the start of Sabine's training: 488 papers, 1.2 MB,
# measured on 2026-10-02.
FIRST_COLLECTION_START = datetime(2026, 5, 1, tzinfo=UTC)


# Python's expat (2.4.1 and later) refuses entity expansion attacks and never fetches
# external entities: the standard library parser is safe on this untrusted feed.
ATOM = "{http://www.w3.org/2005/Atom}"
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"
# The identifier of an arXiv paper, of either form (items.ARXIV_ID), and its version.
PAPER_ID = re.compile(rf"https?://arxiv\.org/abs/({ARXIV_ID})v([0-9]+)")
# arXiv reports an error as a feed whose single entry carries this id.
API_ERROR_ID = re.compile(r"https?://arxiv\.org/api/errors")
ABSTRACT_PAGE_URL = "https://arxiv.org/abs/"


# The name of its raw folders, written once: its instances and its kind use it.
FOLDER_PREFIX = "arxiv_cscr_x_csai"


class ArxivSource:
    name = FOLDER_PREFIX
    extension = "xml"
    acquisition_dir_name = AUTOMATED_WATCH_DIR_NAME

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return the papers submitted since 7 days before last_collected_at; None if none.

        A first collection (last_collected_at is None) reaches back to FIRST_COLLECTION_START.
        """
        now = datetime.now(UTC)
        if last_collected_at is None:
            window_start = FIRST_COLLECTION_START
        else:
            window_start = last_collected_at - ANNOUNCEMENT_DELAY_MARGIN
        raw_response = download_papers(build_search_query(window_start, now))
        paper_count = count_papers(raw_response)
        total_results = read_total_results(raw_response)
        if total_results > paper_count:
            # Failing keeps the last collection date: the next collection asks again.
            raise ValueError(
                f"{total_results} papers found, only {paper_count} returned"
            )
        if paper_count == 0:
            return None
        return raw_response


def build_search_query(window_start: datetime, window_end: datetime) -> str:
    keywords = " OR ".join(
        f'abs:"{keyword}"' if " " in keyword else f"abs:{keyword}"
        for keyword in KEYWORDS
    )
    # The API reads these dates in GMT.
    window_start, window_end = window_start.astimezone(UTC), window_end.astimezone(UTC)
    submission_window = f"{window_start:%Y%m%d%H%M} TO {window_end:%Y%m%d%H%M}"
    return f"cat:cs.CR AND cat:cs.AI AND ({keywords}) AND submittedDate:[{submission_window}]"


def download_papers(search_query: str) -> bytes:
    parameters = {
        "search_query": search_query,
        "start": 0,
        "max_results": PAPERS_PER_PAGE,
        "sortBy": "submittedDate",
        "sortOrder": "ascending",
    }
    return download(f"{API_URL}?{urlencode(parameters)}", API_URL, MAX_RESPONSE_BYTES)


@dataclass(frozen=True)
class Paper:
    """An arXiv paper, at the version the API returned (the latest one)."""

    arxiv_id: str
    version: int
    title: str
    summary: str
    authors: tuple[str, ...]
    published_at: datetime
    updated_at: datetime
    url: str


def read_papers(raw_response: bytes) -> list[Paper]:
    """One paper per valid entry of the feed, in the order of the response.

    An invalid entry is rejected and logged, not guessed: the others are still read.
    """
    papers = []
    for position, entry in enumerate(parse_feed(raw_response).findall(f"{ATOM}entry")):
        try:
            papers.append(parse_paper(entry, position))
        except ValueError as error:
            logger.warning("arXiv paper rejected: %s", error)
    return papers


def count_papers(raw_response: bytes) -> int:
    """Count every entry, valid or not; refuse a feed that reports an API error.

    Entries are validated when read, not here: one malformed paper must not block the
    collection, whose window would keep it forever.
    """
    entries = parse_feed(raw_response).findall(f"{ATOM}entry")
    for entry in entries:
        entry_id = (entry.findtext(f"{ATOM}id") or "").strip()
        if API_ERROR_ID.match(entry_id):
            raise ValueError(f"the arXiv API reports an error: {entry_id!r}")
    return len(entries)


def read_total_results(raw_response: bytes) -> int:
    """The number of papers matching the query, which may exceed the papers of this page."""
    total_results = parse_feed(raw_response).findtext(f"{OPENSEARCH}totalResults")
    if total_results is None or not total_results.strip().isdigit():
        raise ValueError("totalResults is missing or not a number")
    return int(total_results)


def parse_feed(raw_response: bytes) -> ElementTree.Element:
    try:
        feed = ElementTree.fromstring(raw_response)  # noqa: S314 — XML entities: #69
    except ElementTree.ParseError as error:
        raise ValueError(f"not an XML document: {error}") from error
    if feed.tag != f"{ATOM}feed":
        raise ValueError("expected an Atom feed")
    return feed


def parse_paper(entry: ElementTree.Element, position: int) -> Paper:
    label = f"entry {position}"
    entry_id = read_text(entry, "id", label)
    paper_id = PAPER_ID.fullmatch(entry_id)
    if paper_id is None:
        raise ValueError(f"{label}: id is not an arXiv paper: {entry_id!r}")
    arxiv_id, version = paper_id.groups()
    authors = tuple(
        name.text.strip()
        for name in entry.findall(f"{ATOM}author/{ATOM}name")
        if name.text and name.text.strip()
    )
    if not authors:
        raise ValueError(f"{label}: no author")
    return Paper(
        arxiv_id=arxiv_id,
        version=int(version),
        title=read_text(entry, "title", label),
        summary=read_text(entry, "summary", label),
        authors=authors,
        published_at=parse_aware_datetime(
            read_text(entry, "published", label), f"{label}: published"
        ),
        updated_at=parse_aware_datetime(
            read_text(entry, "updated", label), f"{label}: updated"
        ),
        url=ABSTRACT_PAGE_URL + arxiv_id,
    )


def read_text(entry: ElementTree.Element, field: str, label: str) -> str:
    text = (entry.findtext(f"{ATOM}{field}") or "").strip()
    if not text:
        raise ValueError(f"{label}: {field} is missing")
    return text


def convert_paper(paper: Paper, collected_at: datetime, raw_file_path: str) -> Item:
    return Item(
        source_code=SOURCE_CODE,
        source_item_id=paper.arxiv_id,
        kind="paper",
        title=paper.title,
        url=paper.url,
        authors=paper.authors,
        published_at=paper.published_at,
        revised_at=paper.updated_at,
        summary=paper.summary,
        collected_at=collected_at,
        raw_file_path=raw_file_path,
    )


READER: SourceReader[Paper] = SourceReader(SOURCE_CODE, read_papers, convert_paper)
