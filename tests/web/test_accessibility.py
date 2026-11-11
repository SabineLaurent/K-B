"""The criteria of RGAA 4.1.2 (WCAG 2.1 AA) and the rules of Opquast 2025 a test can check on each
page of the site, read by the parser of the standard library: language, title, headings, landmarks,
skip link, current link, lists, decorative images, names of the links, links to another site,
abbreviations, dates (docs/site-web.md, "Accessibilité")."""

import re
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
        self.text_parts: list[str] = []
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
        self.text_parts.append(data)
        if self._open_link is not None:
            self._open_link.text += data
        if self._in_title:
            self.title += data
        if self._english is not None:
            self._english.text.append(data)

    def find_all(self, tag):
        return [attributes for name, attributes in self.tags if name == tag]

    @property
    def text(self):
        """The text of the page, its spaces in a row made one."""
        return " ".join("".join(self.text_parts).split())


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
    # focusable="false" served Internet Explorer only: no attribute of HTML (RGAA 8.2).
    assert all("focusable" not in svg for svg in page.find_all("svg"))


@pytest.mark.parametrize("name", sorted(PAGES))
def test_a_page_has_neither_a_script_nor_a_style_attribute(name):
    page = outline(PAGES[name])

    assert page.find_all("script") == []
    assert [attributes for _, attributes in page.tags if "style" in attributes] == []


def test_the_acknowledgement_of_arxiv_is_a_quotation_in_english():
    page = outline(PAGES["/sources"])

    assert page.find_all("blockquote") == [{"lang": "en"}]
    assert (
        "Thank you to arXiv for use of its open access interoperability."
        in page.texts_in_english
    )


def test_the_word_releases_is_marked_in_english():
    """Absent from the dictionaries of French (RGAA 8.7)."""
    assert "Releases" in outline(PAGES["/sources"]).texts_in_english


@pytest.mark.parametrize("name", sorted(PAGES))
def test_the_links_of_the_footer_are_a_list(name):
    """role="list": Safari drops the semantics of a list whose list-style is none (RGAA 9.3)."""
    footer = re.search(r"<footer\b.*?</footer>", PAGES[name], flags=re.DOTALL)

    assert footer is not None
    assert '<ul class="site-footer-links" role="list">' in footer.group(0)
    assert footer.group(0).count("<a ") == len(
        re.findall(r"<li>\s*<a ", footer.group(0))
    )


@pytest.mark.parametrize("name", sorted(PAGES))
def test_no_space_comes_before_a_colon_or_a_semicolon(name):
    """The rule of Sabine for every text she delivers, the site included (2026-11-11)."""
    assert re.findall(r".{0,20}\s[:;]", outline(PAGES[name]).text) == []


def test_every_link_to_another_site_says_so():
    """Opquast 2025, rule 142."""
    links = [
        link
        for page in map(outline, PAGES.values())
        for link in page.links
        if (link.attributes["href"] or "").startswith("https://")
    ]

    assert links
    assert all("site externe" in link.text for link in links)


def test_the_link_to_a_page_in_english_gives_its_language():
    """Opquast 2025, rule 131: the terms of arXiv are in English."""
    [link] = [
        link
        for link in outline(PAGES["/sources"]).links
        if link.attributes["href"] == "https://info.arxiv.org/help/api/tou.html"
    ]

    assert link.attributes.get("hreflang") == "en"
    assert "en anglais" in link.text


@pytest.mark.parametrize(
    ("name", "abbreviation", "meaning"),
    [
        ("/sources", "API", "interface de programmation"),
        ("/sources", "CISA", "Cybersecurity and Infrastructure Security Agency"),
        (
            "/accessibilite",
            "RGAA",
            "référentiel général d’amélioration de l’accessibilité",
        ),
        ("/accessibilite", "WCAG", "Web Content Accessibility Guidelines"),
        ("500", "UTC", "temps universel coordonné"),
    ],
)
def test_the_first_abbreviation_of_a_page_gives_its_meaning(
    name, abbreviation, meaning
):
    """Opquast 2025, rule 5: at its first occurrence, in brackets, a version number aside."""
    text = outline(PAGES[name]).text
    first = re.search(rf"\b{abbreviation}\b", text)

    assert first is not None
    assert re.match(
        rf"{abbreviation}( [0-9.]+)? \({re.escape(meaning)}\)", text[first.start() :]
    )


def test_the_home_page_says_what_it_holds_and_for_whom():
    """Opquast 2025, rules 99 and 100; the first sentence is the one of the mockups."""
    text = outline(PAGES["/"]).text

    assert (
        "Collecte automatique: arXiv, catalogue CISA KEV, alertes GitHub, releases,"
        " newsletters." in text
    )
    assert "Site privé, réservé à son opératrice." in text


def test_the_sources_name_the_author_of_the_site():
    """Opquast 2025, rules 101 and 114: her name of coder, chosen by Sabine (2026-11-11)."""
    assert "sabl-dev" in outline(PAGES["/sources"]).text


def test_the_accessibility_statement_gives_its_date():
    """Opquast 2025, rule 6."""
    assert outline(PAGES["/accessibilite"]).find_all("time") == [
        {"datetime": "2026-11-11"}
    ]


def test_the_page_500_gives_its_time_and_its_request_id_in_a_list_of_terms():
    page = outline(PAGES["500"])

    assert len(page.find_all("dl")) == 1
    assert len(page.find_all("dt")) == 2
    assert len(page.find_all("time")) == 1


def test_the_note_of_the_page_500_is_in_its_card_out_of_its_list():
    """The mockup puts the note in the card; a p in a dl is no valid HTML (RGAA 8.2)."""
    assert re.search(
        r'<div class="incident">\s*<dl>.*</dl>\s*<p class="incident-note">',
        PAGES["500"],
        flags=re.DOTALL,
    )
