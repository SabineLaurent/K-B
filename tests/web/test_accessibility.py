"""The criteria of RGAA 4.1.2 (WCAG 2.1 AA) a test can check on each page of the site, read by the
parser of the standard library: language, title, headings, landmarks, skip link, current link,
decorative images, names of the links (docs/site-web.md, "Accessibilité")."""

from dataclasses import dataclass, field
from html.parser import HTMLParser
from itertools import pairwise

import pytest
from fastapi.testclient import TestClient
from site_client import OPERATOR_HEADERS, PAGE_PATHS, make_client

from k_b.web.app import create_app

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
LANDMARKS = ("header", "nav", "main", "footer")
SKIP_TARGET = "contenu"


@dataclass
class Link:
    attributes: dict[str, str | None]
    text: str = ""


@dataclass
class EnglishElement:
    """The element marked lang="en" being read: its tag, and how many of its kind are open in it."""

    tag: str
    open_count: int = 1
    text: list[str] = field(default_factory=list)


class PageOutline(HTMLParser):
    """What the checks read of a page: its tags, headings, links, title and texts in English."""

    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.headings: list[str] = []
        self.links: list[Link] = []
        self.title = ""
        self.texts_in_english: list[str] = []
        self._open_link: Link | None = None
        self._in_title = False
        self._english: EnglishElement | None = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        self.tags.append((tag, attributes))
        if self._english is not None and tag == self._english.tag:
            self._english.open_count += 1
        elif self._english is None and attributes.get("lang") == "en":
            self._english = EnglishElement(tag)
        if tag in HEADINGS:
            self.headings.append(tag)
        elif tag == "a":
            self._open_link = Link(attributes)
            self.links.append(self._open_link)
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._open_link = None
        elif tag == "title":
            self._in_title = False
        if self._english is not None and tag == self._english.tag:
            self._english.open_count -= 1
            if not self._english.open_count:
                self.texts_in_english.append(
                    " ".join("".join(self._english.text).split())
                )
                self._english = None

    def handle_data(self, data):
        if self._open_link is not None:
            self._open_link.text += data
        if self._in_title:
            self.title += data
        if self._english is not None:
            self._english.text.append(data)

    def find_all(self, tag):
        return [attributes for name, attributes in self.tags if name == tag]


def outline(text):
    parser = PageOutline()
    parser.feed(text)
    return parser


def fetch_every_page():
    """Each page the site may answer, by its name: the pages, and the errors 403, 404, 405 and 500."""
    client = make_client()
    failing_app = create_app(operator_id=None)

    @failing_app.get("/failing")
    def fail() -> None:
        raise RuntimeError

    failing_client = TestClient(
        failing_app, base_url="http://localhost", raise_server_exceptions=False
    )
    pages = {path: client.get(path, headers=OPERATOR_HEADERS) for path in PAGE_PATHS}
    pages["403"] = client.get("/")
    pages["404"] = client.get("/no-such-page", headers=OPERATOR_HEADERS)
    pages["405"] = client.post("/", headers=OPERATOR_HEADERS)
    pages["500"] = failing_client.get("/failing")
    return {name: response.text for name, response in pages.items()}


PAGES = fetch_every_page()


@pytest.mark.parametrize("name", sorted(PAGES))
def test_a_page_is_an_html_document_in_french(name):
    assert PAGES[name].startswith("<!DOCTYPE html>")
    assert outline(PAGES[name]).find_all("html") == [{"lang": "fr"}]


def test_each_page_has_a_title_of_its_own_ending_with_the_name_of_the_site():
    titles = [outline(text).title for text in PAGES.values()]

    assert all(title.endswith(" · K-B") for title in titles)
    assert len(set(titles)) == len(titles)


@pytest.mark.parametrize("name", sorted(PAGES))
def test_a_page_has_one_h1_first_and_no_level_skipped(name):
    levels = [int(heading[1]) for heading in outline(PAGES[name]).headings]

    assert levels[0] == 1
    assert levels.count(1) == 1
    assert all(level <= previous + 1 for previous, level in pairwise(levels))


@pytest.mark.parametrize("name", sorted(PAGES))
def test_a_page_has_each_landmark_once_its_navigation_named(name):
    page = outline(PAGES[name])

    assert [len(page.find_all(landmark)) for landmark in LANDMARKS] == [1, 1, 1, 1]
    assert page.find_all("nav")[0].get("aria-label")
    assert page.find_all("main")[0].get("id") == SKIP_TARGET


@pytest.mark.parametrize("name", sorted(PAGES))
def test_the_first_link_skips_to_the_content(name):
    first_link = outline(PAGES[name]).links[0]

    assert first_link.attributes["href"] == f"#{SKIP_TARGET}"
    assert first_link.text.strip() == "Aller au contenu"


@pytest.mark.parametrize(
    ("name", "current"),
    [
        ("/", ["/"]),
        ("/sources", ["/sources"]),
        ("/accessibilite", ["/accessibilite"]),
        ("404", []),
    ],
)
def test_only_the_link_of_the_current_page_is_marked(name, current):
    marked = [
        link.attributes["href"]
        for link in outline(PAGES[name]).links
        if link.attributes.get("aria-current") == "page"
    ]

    assert marked == current


@pytest.mark.parametrize("name", sorted(PAGES))
def test_every_link_has_a_name_and_every_svg_is_decorative(name):
    page = outline(PAGES[name])

    assert all(link.text.strip() for link in page.links)
    assert all(svg.get("aria-hidden") == "true" for svg in page.find_all("svg"))


@pytest.mark.parametrize("name", sorted(PAGES))
def test_a_page_has_neither_a_script_nor_a_style_attribute(name):
    page = outline(PAGES[name])

    assert page.find_all("script") == []
    assert [attributes for _, attributes in page.tags if "style" in attributes] == []


def test_the_acknowledgement_of_arxiv_is_marked_in_english():
    assert (
        "Thank you to arXiv for use of its open access interoperability."
        in outline(PAGES["/sources"]).texts_in_english
    )


def test_the_page_500_gives_its_time_and_its_request_id_in_a_list_of_terms():
    page = outline(PAGES["500"])

    assert len(page.find_all("dl")) == 1
    assert len(page.find_all("dt")) == 2
    assert len(page.find_all("time")) == 1
