import logging
from datetime import date
from pathlib import Path

from k_b.tldr_editions import TldrArticle, read_articles, read_edition_date, read_page_title

FIXTURES_DIR = Path(__file__).parent / "fixtures"
RECORDED_PAGE = (FIXTURES_DIR / "tldr_ai_extract.html").read_bytes()
LANDING_PAGE = b"<html><body><h1>Keep up with AI in 5 minutes</h1></body></html>"
PAGE_NAME = "tldr_ai 2026-10-01"


def page_with_article(link: str, title: str = "A title (2 minute read)") -> bytes:
    return (
        '<html><body><h1>TLDR AI 2026-10-01</h1><section><article class="mt-3">'
        f'<a class="font-bold" href="{link}"><h3>{title}</h3></a>'
        '<div class="newsletter-html">A summary.</div></article></section></body></html>'
    ).encode()


def test_the_edition_date_is_read_from_the_page_title():
    assert read_edition_date(RECORDED_PAGE, edition_title="AI") == date(2026, 10, 1)


def test_a_page_that_is_not_an_edition_has_no_date():
    # A day without an edition redirects to the landing page of the newsletter.
    assert read_edition_date(LANDING_PAGE, edition_title="AI") is None


def test_a_page_of_another_edition_has_no_date():
    other_edition = RECORDED_PAGE.replace(b"TLDR AI 2026", b"TLDR Dev 2026")

    assert read_edition_date(other_edition, edition_title="AI") is None


def test_an_edition_title_is_matched_literally():
    page = b"<html><body><h1>TLDR Information Security 2026-10-01</h1></body></html>"

    assert read_edition_date(page, edition_title="Information Security") == date(2026, 10, 1)
    assert read_edition_date(page, edition_title="Information.Security") is None


def test_one_article_per_entry_without_the_sponsored_ones():
    articles = read_articles(RECORDED_PAGE, PAGE_NAME)

    assert [article.title for article in articles] == [
        "Musk's SpaceXAI Considers Overhaul of Pricing for Grok, X Users (1 minute read)",
        "We can and must solve alignment (14 minute read)",
    ]


def test_an_article_keeps_its_link_without_the_tracking_parameters():
    articles = read_articles(RECORDED_PAGE, PAGE_NAME)

    assert articles[0].url == "https://links.tldrnewsletter.com/VezRJB"
    assert articles[1].url == "https://www.goodfire.com/blog/we-can-and-must-solve-alignment?ref=k-b"


def test_the_summary_is_plain_text():
    article = read_articles(RECORDED_PAGE, PAGE_NAME)[1]

    assert article == TldrArticle(
        title="We can and must solve alignment (14 minute read)",
        url="https://www.goodfire.com/blog/we-can-and-must-solve-alignment?ref=k-b",
        summary="A summary on interpretability as the main challenge of alignment. "
        "Second paragraph.",
    )


def test_a_doubly_escaped_link_is_unescaped_before_its_tracking_is_removed():
    page = page_with_article("https://example.org/?id=7&amp;amp;utm_source=tldrai&amp;amp;x=1")

    assert read_articles(page, PAGE_NAME)[0].url == "https://example.org/?id=7&x=1"


def test_an_article_whose_link_is_not_https_is_rejected():
    assert read_articles(page_with_article("javascript:alert(1)"), PAGE_NAME) == []
    assert read_articles(page_with_article("http://example.org/"), PAGE_NAME) == []


def test_an_article_without_a_title_is_rejected():
    assert read_articles(page_with_article("https://example.org/", title=""), PAGE_NAME) == []


def test_a_page_without_any_article_gives_no_article():
    assert read_articles(LANDING_PAGE, PAGE_NAME) == []


def test_the_page_title_is_read_as_written():
    assert read_page_title(LANDING_PAGE) == "Keep up with AI in 5 minutes"
    assert read_page_title(b"<html><body><p>no title</p></body></html>") == ""


def test_a_rejected_article_is_logged_with_its_page(caplog):
    with caplog.at_level(logging.WARNING, logger="k_b.tldr_editions"):
        read_articles(page_with_article("http://example.org/"), PAGE_NAME)

    assert "tldr_ai 2026-10-01: article 0 rejected, no title or no https link" in caplog.text
