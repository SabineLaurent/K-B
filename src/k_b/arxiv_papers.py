"""Read the papers of a raw arXiv API response (an Atom feed)."""

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from datetime import datetime

# Python's expat (2.4.1 and later) refuses entity expansion attacks and never fetches
# external entities: the standard library parser is safe on this untrusted feed.
ATOM = "{http://www.w3.org/2005/Atom}"
OPENSEARCH = "{http://a9.com/-/spec/opensearch/1.1/}"
# Only papers numbered since 2007 (YYMM.NNNNN) are expected in cs.CR × cs.AI.
PAPER_ID = re.compile(r"https?://arxiv\.org/abs/(\d{4}\.\d{4,5})v(\d+)")
ABSTRACT_PAGE_URL = "https://arxiv.org/abs/"


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
    """One paper per entry of the feed, in the order of the response."""
    entries = parse_feed(raw_response).findall(f"{ATOM}entry")
    return [parse_paper(entry, position) for position, entry in enumerate(entries)]


def read_total_results(raw_response: bytes) -> int:
    """The number of papers matching the query, which may exceed the papers of this page."""
    total_results = parse_feed(raw_response).findtext(f"{OPENSEARCH}totalResults")
    if total_results is None or not total_results.strip().isdigit():
        raise ValueError("totalResults is missing or not a number")
    return int(total_results)


def parse_feed(raw_response: bytes) -> ElementTree.Element:
    try:
        feed = ElementTree.fromstring(raw_response)
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
        published_at=read_date(entry, "published", label),
        updated_at=read_date(entry, "updated", label),
        url=ABSTRACT_PAGE_URL + arxiv_id,
    )


def read_text(entry: ElementTree.Element, field: str, label: str) -> str:
    text = (entry.findtext(f"{ATOM}{field}") or "").strip()
    if not text:
        raise ValueError(f"{label}: {field} is missing")
    return text


def read_date(entry: ElementTree.Element, field: str, label: str) -> datetime:
    """Refuse a date without a time zone: arXiv dates are UTC, written with a final Z."""
    text = read_text(entry, field, label)
    try:
        parsed_date = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"{label}: {field} is invalid: {text!r}") from error
    if parsed_date.tzinfo is None:
        raise ValueError(f"{label}: {field} has no time zone")
    return parsed_date
