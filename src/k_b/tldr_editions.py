"""Read the articles of a TLDR edition page, as tldr.tech publishes it."""

import logging
import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# The title of an edition page, e.g. "TLDR AI 2026-10-01"; the landing page has no date.
EDITION_TITLE = re.compile(r"TLDR .+ (\d{4}-\d{2}-\d{2})")
SPONSOR_MARK = "(Sponsor)"


@dataclass(frozen=True)
class TldrArticle:
    title: str
    url: str
    summary: str


def read_edition_date(page: bytes) -> date | None:
    """Return the date in the page title, or None if the page is not an edition."""
    title = BeautifulSoup(page, "html.parser").select_one("h1")
    match = EDITION_TITLE.fullmatch(title.get_text(strip=True)) if title else None
    return date.fromisoformat(match.group(1)) if match else None


def read_articles(page: bytes) -> list[TldrArticle]:
    """One article per entry of the edition, sponsored entries left out.

    An invalid entry is rejected and logged, not guessed: the others are still read.
    """
    articles = []
    for position, entry in enumerate(BeautifulSoup(page, "html.parser").select("article")):
        link = entry.select_one("a.font-bold")
        title = link.get_text(strip=True) if link else ""
        if SPONSOR_MARK in title:
            continue
        href = link.get("href") if link else None
        url = remove_tracking(href) if isinstance(href, str) else None
        if not title or url is None:
            logger.warning("TLDR article %d rejected: no title or no https link", position)
            continue
        summary = entry.select_one("div.newsletter-html")
        articles.append(
            TldrArticle(
                title=title,
                url=url,
                summary=summary.get_text(" ", strip=True) if summary else "",
            )
        )
    return articles


def remove_tracking(href: str) -> str | None:
    """Return the https link without its utm_* parameters; None if it is not an https link.

    The parameters are filtered as written, so the others keep their exact encoding.
    """
    # Some links are escaped twice in the page: "&amp;" is still there once the HTML is parsed.
    parts = urlsplit(href.replace("&amp;", "&"))
    if parts.scheme != "https" or not parts.netloc:
        return None
    kept_parameters = [
        parameter
        for parameter in parts.query.split("&")
        if parameter and not parameter.startswith("utm_")
    ]
    return urlunsplit(parts._replace(query="&".join(kept_parameters)))
