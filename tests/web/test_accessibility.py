"""The criteria of RGAA 4.1.2 (WCAG 2.1 AA) and the rules of Opquast 2025 a test can check on each
page of the site, read by the parser of the standard library: language, title, headings, landmarks,
skip link, current link, lists, decorative images, names of the links, links to another site,
abbreviations, dates, fields and their errors (docs/site-web.md, "Accessibilité")."""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from itertools import pairwise

import pytest
from fastapi.testclient import TestClient
from feed_fixture import make_page
from item_fixture import (
    ADVISORY_ABSENT_FROM_CATALOG,
    ADVISORY_IN_CATALOG,
    ADVISORY_WITHOUT_CVE,
    NEWSLETTER_ARTICLE,
    PAPER,
    RELEASE,
    VULNERABILITY,
    WITHDRAWN_VULNERABILITY,
    make_detail,
)
from site_client import OPERATOR_HEADERS, PAGE_PATHS, make_app, make_client, serve
from trends_fixture import TRENDS

HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
# Once each; nav at least once, each named.
LANDMARKS = ("header", "main", "footer")
SKIP_TARGET = "contenu"
# The feed refused on its three fields: a search too long, a kind out of the five, date without day.
FEED_REFUSED = "/?q=" + "a" * 201 + "&kind=clip&period=date"
FEED_PAGES = ("/", "/?page=2", "feed-empty", "feed-refused")
# The detail of each kind and of each state of its banner, by name; the variants have an identifier
# of their own, as each page has a title of its own.
ITEM_PAGES = {
    "item-paper": make_detail(PAPER),
    "item-vulnerability": make_detail(VULNERABILITY),
    "item-vulnerability-withdrawn": make_detail(WITHDRAWN_VULNERABILITY),
    "item-advisory-in-catalog": make_detail(ADVISORY_IN_CATALOG),
    "item-advisory-absent": make_detail(ADVISORY_ABSENT_FROM_CATALOG),
    "item-advisory-without-cve": make_detail(ADVISORY_WITHOUT_CVE),
    "item-advisory-without-package": make_detail(
        ADVISORY_ABSENT_FROM_CATALOG, packages=[], ghsa_id="GHSA-2222-3333-4444"
    ),
    "item-release": make_detail(RELEASE),
    "item-release-without-notes": make_detail(RELEASE, body=None, tag_name="v2.1.285"),
    "item-newsletter-article": make_detail(NEWSLETTER_ARTICLE),
}
ADVISORY_PAGES = (
    "item-advisory-in-catalog",
    "item-advisory-absent",
    "item-advisory-without-cve",
)
VULNERABILITY_PAGES = ("item-vulnerability", "item-vulnerability-withdrawn")
TRENDS_NOT_FOUND = {"error": "trend_window_not_found"}
# The trends in each state, by name: their address, and the answer of the data API.
TREND_PAGES = {
    "/tendances": ("/tendances", serve(TRENDS)),
    "trends-refused": ("/tendances?window_end=2026-02-30", serve(TRENDS)),
    "trends-absent": (
        "/tendances?window_end=2026-10-11",
        serve(TRENDS_NOT_FOUND, status_code=404),
    ),
    "trends-empty": ("/tendances", serve(TRENDS_NOT_FOUND, status_code=404)),
}


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
    failing_app = make_app(operator_id=None)

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
    pages["/?page=2"] = make_client(handler=serve(make_page(20, total=45))).get(
        "/?page=2", headers=OPERATOR_HEADERS
    )
    pages["feed-empty"] = make_client(handler=serve(make_page(0))).get(
        "/", headers=OPERATOR_HEADERS
    )
    pages["feed-refused"] = client.get(FEED_REFUSED, headers=OPERATOR_HEADERS)
    for name, detail in ITEM_PAGES.items():
        pages[name] = make_client(handler=serve(detail)).get(
            f"/items/{detail['id']}", headers=OPERATOR_HEADERS
        )
    for name, (path, handler) in TREND_PAGES.items():
        pages[name] = make_client(handler=handler).get(path, headers=OPERATOR_HEADERS)
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
def test_a_page_has_each_landmark_once_each_navigation_named(name):
    """RGAA 12.6: the pagination is a second navigation, named apart from the first."""
    page = outline(PAGES[name])
    names = [nav.get("aria-label") for nav in page.find_all("nav")]

    assert [len(page.find_all(landmark)) for landmark in LANDMARKS] == [1, 1, 1]
    assert names
    assert all(names)
    assert len(set(names)) == len(names)
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
        # The detail of an item is not the feed (Veille).
        ("item-paper", []),
        ("/tendances", ["/tendances"]),
        ("trends-refused", ["/tendances"]),
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


def find_links(is_to_another_site):
    """The links of every page, to another site (http or https) or within the site."""
    return [
        link
        for page in map(outline, PAGES.values())
        for link in page.links
        if (link.attributes["href"] or "").startswith(("http://", "https://"))
        == is_to_another_site
    ]


def test_every_link_to_another_site_has_the_same_form_its_arrow_held_to_its_text():
    """Opquast 2025, rule 138: on the feed as on /sources, the arrow then the announcement, smaller;
    a no-break space before the arrow, which never begins a line alone."""
    links = re.findall(
        r'<a [^>]*href="https?://[^"]*"[^>]*>(.*?)</a>',
        "".join(PAGES.values()),
        flags=re.DOTALL,
    )

    assert links
    assert all(
        re.search(
            r'<span aria-hidden="true">&nbsp;↗</span> <span class="link-note">\(.*nouvel'
            r" onglet\)</span>$",
            link,
        )
        for link in links
    )


def test_every_link_to_another_site_says_so_and_opens_a_new_tab_it_announces():
    """Opquast 2025, rules 142 and 146 (Sabine, 2026-11-11: to stay in K-B): the new tab said in the
    text of the link, which a screen reader reads too; noopener and noreferrer, so that the page
    opened reaches neither the page of K-B nor its address."""
    links = find_links(is_to_another_site=True)

    assert links
    assert all("site externe, nouvel onglet" in link.text for link in links)
    assert all(link.attributes.get("target") == "_blank" for link in links)
    assert all(
        {"noopener", "noreferrer"} <= set((link.attributes.get("rel") or "").split())
        for link in links
    )


def test_a_link_within_the_site_opens_in_the_same_tab():
    """Opquast 2025, rule 138: the links of the same nature behave the same."""
    links = find_links(is_to_another_site=False)

    assert links
    assert all("target" not in link.attributes for link in links)


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
        ("/", "KEV", "Known Exploited Vulnerabilities"),
        ("/", "CISA", "Cybersecurity and Infrastructure Security Agency"),
        *(
            (name, abbreviation, meaning)
            for name in (*VULNERABILITY_PAGES, *ADVISORY_PAGES)
            for abbreviation, meaning in (
                ("CVE", "Common Vulnerabilities and Exposures"),
                ("KEV", "Known Exploited Vulnerabilities"),
                ("CISA", "Cybersecurity and Infrastructure Security Agency"),
            )
        ),
    ],
)
def test_the_first_abbreviation_of_a_page_gives_its_meaning(
    name, abbreviation, meaning
):
    """Opquast 2025, rule 5: at its first occurrence, in brackets, a version number aside; an
    identifier such as CVE-2020-29583 is not the abbreviation."""
    text = outline(PAGES[name]).text
    first = re.search(rf"\b{abbreviation}\b(?!-)", text)

    assert first is not None
    assert re.match(
        rf"{abbreviation}( [0-9.]+)? \({re.escape(meaning)}\)", text[first.start() :]
    )


def test_the_home_page_says_what_it_holds_and_for_whom():
    """Opquast 2025, rules 99 and 100; the first sentence is the one of the mockups, KEV and CISA
    given their meaning (rule 5)."""
    text = outline(PAGES["/"]).text

    assert (
        "Collecte automatique: arXiv, catalogue KEV (Known Exploited Vulnerabilities) de la"
        " CISA (Cybersecurity and Infrastructure Security Agency), alertes GitHub, releases,"
        " newsletters." in text
    )
    assert "Site privé, réservé à son opératrice." in text


def test_the_sources_name_the_author_of_the_site():
    """Opquast 2025, rules 101 and 114: her name of coder, chosen by Sabine (2026-11-11)."""
    assert "sabl-dev" in outline(PAGES["/sources"]).text


def test_the_accessibility_statement_gives_its_date():
    """Opquast 2025, rule 6: established, then updated."""
    assert outline(PAGES["/accessibilite"]).find_all("time") == [
        {"datetime": "2026-11-11"},
        {"datetime": "2026-11-13"},
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


def find_ids(page):
    return {attributes["id"] for _, attributes in page.tags if attributes.get("id")}


@pytest.mark.parametrize("name", FEED_PAGES)
def test_every_field_of_the_feed_has_its_label(name):
    """RGAA 11.1; WCAG 1.3.1 and 4.1.2: each input named by a label tied to its id."""
    page = outline(PAGES[name])
    inputs = page.find_all("input")
    labelled = {label.get("for") for label in page.find_all("label")}

    assert len(inputs) == 11
    assert all(field.get("id") in labelled for field in inputs)
    assert [button.get("type") for button in page.find_all("button")] == ["submit"]


@pytest.mark.parametrize("name", FEED_PAGES)
def test_each_group_of_the_feed_is_a_fieldset_with_its_legend_first(name):
    """RGAA 11.5 and 11.6."""
    assert re.findall(r"<fieldset[^>]*>\s*<legend>([^<]+)</legend>", PAGES[name]) == [
        "Sortes",
        "Depuis",
    ]


@pytest.mark.parametrize("name", sorted(PAGES))
def test_every_reference_of_aria_names_an_element_of_the_page(name):
    page = outline(PAGES[name])
    ids = find_ids(page)
    references = [
        reference
        for _, attributes in page.tags
        for reference in (attributes.get("aria-describedby") or "").split()
    ]

    assert all(reference in ids for reference in references)


def test_each_field_refused_says_why_under_it_and_in_the_summary():
    """RGAA 11.10 and 11.11; WCAG 3.3.1 to 3.3.3: the message tied to its field, the field marked
    invalid, the summary linking to each field, the values kept."""
    page = outline(PAGES["feed-refused"])
    ids = find_ids(page)
    tied = {
        attributes["id"]: attributes.get("aria-describedby", "").split()
        for tag, attributes in page.tags
        if tag in ("input", "fieldset") and attributes.get("aria-describedby")
    }
    summary_links = [
        link.attributes["href"]
        for link in page.links
        if link.attributes["href"].startswith("#")
        and link.attributes["href"] != "#contenu"
    ]

    assert summary_links == ["#q", "#kinds", "#start"]
    assert all(link[1:] in ids for link in summary_links)
    # The error first, then the help: the reason of the refusal is heard first.
    assert tied["q"] == ["q-error", "q-help"]
    assert tied["kinds"] == ["kinds-error", "kinds-help"]
    assert tied["start"] == ["start-error", "start-help"]
    invalid = [
        attributes["id"]
        for _, attributes in page.tags
        if attributes.get("aria-invalid") == "true"
    ]
    assert invalid == ["q", "start"]


def test_the_feed_refused_shows_no_card():
    assert '<li class="card">' not in PAGES["feed-refused"]


def test_the_cards_are_a_list_their_titles_level_two():
    """RGAA 9.1 and 9.3."""
    page = outline(PAGES["/"])

    assert '<ul class="cards" role="list">' in PAGES["/"]
    assert PAGES["/"].count('<li class="card">') == 14
    assert page.headings.count("h2") == 14


def test_the_titles_given_in_english_are_marked_and_the_word_release():
    """RGAA 8.7: the titles of papers, vulnerabilities, advisories and newsletters, the kind
    Release and the box Releases; the title of a release, a name and a version, is not."""
    english = outline(PAGES["/"]).texts_in_english

    assert "Mistral Large 4 (9 minute read)" in english
    assert "Apple Multiple Products Out-of-Bounds Write Vulnerability" in english
    assert "Release" in english
    assert "Releases" in english
    assert "anthropics/claude-code v2.1.286" not in english


def test_the_dates_of_the_cards_are_time_elements_with_their_month_in_letters():
    """Opquast 2025, rules 4 and 231."""
    days = re.findall(r'<time datetime="([0-9-]+)">([^<]+)</time>', PAGES["/"])

    assert len(days) == 14
    assert all(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", day) for day, _ in days)
    assert all(
        re.fullmatch(r"(1er|[0-9]{1,2}) [a-zéû]+ [0-9]{4}", text) for _, text in days
    )


def test_the_exploited_mark_is_a_word_not_a_colour():
    """RGAA 3.1: the state is written; three items of the fixture are in the catalog, a fourth was
    withdrawn from it."""
    assert PAGES["/"].count('<span class="badge">Exploitée (KEV)</span>') == 3


def test_the_pagination_is_named_and_gives_the_page():
    page = outline(PAGES["/?page=2"])

    assert [nav.get("aria-label") for nav in page.find_all("nav")] == [
        "Navigation principale",
        "Pagination",
    ]
    assert "Page 2 sur 3" in page.text


def test_the_rules_of_a_field_are_written_before_sending():
    """WCAG 3.3.2 (A), RGAA 11.10.1, Opquast 70 and 71: the start date is required with Date only,
    and no kind checked is the five; neither can be said by required without a script."""
    page = outline(PAGES["/"])
    described = {
        attributes["id"]: attributes.get("aria-describedby")
        for tag, attributes in page.tags
        if tag in ("input", "fieldset")
    }
    helps = dict(
        re.findall(r'<p id="([a-z]+-help)" class="field-help">([^<]+)</p>', PAGES["/"])
    )

    assert described["q"] == "q-help"
    assert described["kinds"] == "kinds-help"
    assert described["start"] == "start-help"
    assert "Obligatoire avec « Date »" in helps["start-help"]
    assert "les cinq sortes" in helps["kinds-help"]


@pytest.mark.parametrize("name", sorted(ITEM_PAGES))
def test_a_detail_has_its_texts_of_the_source_in_english(name):
    """RGAA 8.7: the title, as on the feed (the title of a release, a repository and a name, is
    not), the vendor and the product; the summary, the description and the notes by their
    paragraphs."""
    page = outline(PAGES[name])
    detail = ITEM_PAGES[name]

    assert (detail["title"] in page.texts_in_english) is (detail["kind"] != "release")
    assert all(
        'lang="en"' in paragraph
        for paragraph in re.findall(
            r'<section class="item-text"[^>]*>.*?</section>',
            PAGES[name],
            flags=re.DOTALL,
        )
        for paragraph in re.findall(r"<p[^>]*>", paragraph)
    )
    for name_of_field in ("vendor", "product"):
        if name_of_field in detail:
            assert detail[name_of_field] in page.texts_in_english


@pytest.mark.parametrize("name", sorted(ITEM_PAGES))
def test_the_facts_of_a_detail_are_a_list_of_terms_each_with_its_value(name):
    """RGAA 9.3: each dt followed by its dd, in a div of the dl."""
    for facts in re.findall(
        r'<dl class="item-facts">(.*?)</dl>', PAGES[name], flags=re.DOTALL
    ):
        groups = re.findall(
            r"<div[^>]*>\s*(<dt>.*?</dt>)\s*(<dd[^>]*>.*?</dd>)\s*</div>",
            facts,
            flags=re.DOTALL,
        )
        assert len(groups) == facts.count("<dt>") == facts.count("<dd")


@pytest.mark.parametrize("name", sorted(ITEM_PAGES))
def test_the_dates_of_a_detail_are_time_elements_with_their_month_in_letters(name):
    days = re.findall(r'<time datetime="([0-9-]+)">([^<]+)</time>', PAGES[name])

    assert days
    assert all(
        re.fullmatch(r"(1er|[0-9]{1,2}) [a-zéû]+ [0-9]{4}", text) for _, text in days
    )


@pytest.mark.parametrize("name", sorted(ITEM_PAGES))
def test_the_meaning_of_an_abbreviation_is_in_italics_and_in_english(name):
    """As on the feed, /sources and the statement: <i lang="en">."""
    openings = re.findall(r'\((<[a-z]+) lang="en">', PAGES[name])

    assert all(opening == "<i" for opening in openings)


def test_the_statement_says_its_limits_of_the_detail():
    """RGAA 9.1 and 9.3: the notes of a release are plain text (D3); RGAA 8.7: the language of the
    texts of the sources is a hypothesis."""
    text = outline(PAGES["/accessibilite"]).text

    assert "texte brut" in text
    assert "hypothèse" in text
    assert "le sens de chaque sigle" not in text
    assert "TLDR, nom de la newsletter, n’est pas développé" in text


@pytest.mark.parametrize("name", sorted(PAGES))
def test_the_navigation_leads_to_the_feed_and_to_the_trends(name):
    """Sabine, 2026-11-11: both links in sight at every width, no menu folded."""
    navigation = re.search(
        r'<div class="site-nav-links">(.*?)</div>', PAGES[name], flags=re.DOTALL
    )

    assert navigation is not None
    assert [
        (link.attributes["href"], link.text)
        for link in outline(navigation.group(1)).links
    ] == [("/", "Veille"), ("/tendances", "Tendances")]


def test_the_page_not_found_leads_to_the_feed_and_to_the_trends():
    """C10: the tree of the mockups (Maquette-404.dc.html)."""
    actions = re.search(
        r'<div class="error-actions">(.*?)</div>', PAGES["404"], flags=re.DOTALL
    )

    assert actions is not None
    assert [
        (link.attributes["href"], " ".join(link.text.split()))
        for link in outline(actions.group(1)).links
    ] == [("/", "← Retour au fil de veille"), ("/tendances", "Voir les tendances")]


def test_the_sources_name_gh_archive_for_the_trends():
    assert "Tendances: GH Archive" in outline(PAGES["/sources"]).text


def test_the_table_of_the_trends_has_its_caption_and_a_header_for_each_column():
    """RGAA 5.4, 5.6 and 5.7; WCAG 1.3.1: the caption first in the table, a th scope="col" for each
    column, with the words of Maquette-tendances.dc.html, and in each row its repository in a
    th scope="row" between three cells."""
    table = re.search(
        r"<table\b[^>]*>(.*?)</table>", PAGES["/tendances"], flags=re.DOTALL
    )

    assert table is not None
    assert re.match(r"\s*<caption\b", table.group(1))
    head = re.search(r"<thead>(.*?)</thead>", table.group(1), flags=re.DOTALL)
    assert head is not None
    headers = re.findall(r"<th\b([^>]*)>(.*?)</th>", head.group(1), flags=re.DOTALL)
    assert [" ".join(re.sub(r"<[^>]+>", "", text).split()) for _, text in headers] == [
        "Rang",
        "Dépôt",
        "Étoiles gagnées",
        "Forks gagnés",
    ]
    assert all('scope="col"' in attributes for attributes, _ in headers)
    body = re.search(r"<tbody>(.*?)</tbody>", table.group(1), flags=re.DOTALL)
    assert body is not None
    rows = re.findall(r"<tr>(.*?)</tr>", body.group(1), flags=re.DOTALL)
    assert [re.findall(r"<(td|th)\b([^>]*)>", row)[:4] for row in rows] == [
        [
            ("td", ' class="rank"'),
            ("th", ' scope="row"'),
            ("td", ' class="number"'),
            ("td", ' class="number"'),
        ]
    ] * 5


def test_the_window_of_the_trends_is_given_by_two_time_elements():
    """Opquast 2025, rules 4 and 231: its first and its last day, the month in letters."""
    caption = re.search(
        r"<caption\b[^>]*>(.*?)</caption>", PAGES["/tendances"], flags=re.DOTALL
    )

    assert caption is not None
    assert re.findall(
        r'<time datetime="([0-9-]+)">([^<]+)</time>', caption.group(1)
    ) == [
        ("2026-10-08", "8 octobre 2026"),
        ("2026-10-10", "10 octobre 2026"),
    ]


def test_the_trends_say_their_sample_and_their_order():
    """C6: never stars gained from GH Archive without saying it (docs/specs-collecte.md, "Limite
    mesurée le 2026-10-29"); the order of GET /trends (docs/specs-api.md)."""
    text = outline(PAGES["/tendances"]).text

    assert (
        "qui ne voit qu’environ 1 % des étoiles et de 0,8 à 1,3 % des forks, jusqu’à 4,2 %"
        in text
    )
    assert "triés par étoiles gagnées, puis par forks" in text
    assert "Jusqu’à 60" not in text


@pytest.mark.parametrize("name", sorted(TREND_PAGES))
def test_gh_archive_is_explained_at_its_first_occurrence(name):
    """Opquast 2025, rule 5: in the words of /sources."""
    text = outline(PAGES[name]).text

    assert text[text.index("GH Archive") :].startswith(
        "GH Archive (l’archive des événements publics de GitHub)"
    )


def test_the_word_forks_is_marked_in_english():
    """Absent from the dictionaries of French (RGAA 8.7)."""
    english = outline(PAGES["/tendances"]).texts_in_english

    assert "forks" in english
    assert "Forks" in english


@pytest.mark.parametrize("name", sorted(TREND_PAGES))
def test_the_field_of_the_trends_has_its_label_and_its_help(name):
    """RGAA 11.1 and 11.10; WCAG 1.3.1, 3.3.2 and 4.1.2."""
    page = outline(PAGES[name])
    labelled = {label.get("for") for label in page.find_all("label")}
    [field] = page.find_all("input")

    assert field.get("id") in labelled
    assert field.get("type") == "date"
    assert "window-end-help" in (field.get("aria-describedby") or "").split()
    assert [button.get("type") for button in page.find_all("button")] == ["submit"]


def test_the_day_refused_says_why_under_its_field():
    """RGAA 11.10 and 11.11; WCAG 3.3.1: the message tied to its field, heard first, the field
    marked invalid; one field, no summary."""
    page = outline(PAGES["trends-refused"])
    [field] = page.find_all("input")

    assert field.get("aria-describedby") == "window-end-error window-end-help"
    assert field.get("aria-invalid") == "true"
    assert "error-summary" not in PAGES["trends-refused"]


def test_the_statement_says_what_the_tests_check_of_the_table():
    assert (
        "le tableau des tendances, avec sa légende et l’en-tête de chaque colonne"
        in (outline(PAGES["/accessibilite"]).text)
    )


def test_the_frame_of_the_table_scrolls_by_the_keyboard_named_by_its_caption():
    """A table of 560 px at least, as Maquette-tendances.dc.html, scrolls in its frame on a narrower
    screen; WCAG 2.1.1 asks the keyboard, without script: the frame takes the focus, a region
    named by the caption."""
    page = outline(PAGES["/tendances"])
    [frame] = [
        attributes
        for tag, attributes in page.tags
        if tag == "div" and attributes.get("class") == "table-frame"
    ]
    [caption] = page.find_all("caption")

    assert (frame.get("role"), frame.get("tabindex")) == ("region", "0")
    assert frame.get("aria-labelledby") == caption.get("id")
    assert caption.get("id")
