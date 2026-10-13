import re
import typing
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from k_b.items import Highlight, Item, SourceCode

SEED_SOURCES = (
    Path(__file__).parent.parent / "src" / "k_b" / "database" / "seed_sources.sql"
)
COLLECTED_AT = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
RAW_FILE_PATH = "automated_watch/arxiv_cscr_x_csai/2026-10-05T093000Z.xml"


def item_fields(**changes):
    """A paper, with every field its kind requires."""
    fields = {
        "source_code": "arxiv",
        "source_item_id": "2509.12345",
        "kind": "paper",
        "title": "A paper",
        "url": "https://arxiv.org/abs/2509.12345",
        "authors": ("Ada Lovelace",),
        "published_at": datetime(2025, 9, 15, 17, 0, tzinfo=UTC),
        "revised_at": datetime(2025, 9, 20, 12, 0, tzinfo=UTC),
        "summary": "What it says.",
        "collected_at": COLLECTED_AT,
        "raw_file_path": RAW_FILE_PATH,
    }
    fields.update(changes)
    return fields


def vulnerability_fields(**changes):
    """A CISA KEV vulnerability, with every field its kind requires."""
    fields = {
        "source_code": "cisa_kev",
        "source_item_id": "CVE-2026-86950",
        "kind": "vulnerability",
        "title": "Apple Multiple Products Out-of-Bounds Write Vulnerability",
        "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-86950",
        "published_at": datetime(2026, 9, 29, tzinfo=UTC),
        "summary": "An out-of-bounds write.",
        "collected_at": COLLECTED_AT,
        "raw_file_path": "automated_watch/cisa_kev/2026-10-05T093000Z.csv",
        "cve": "CVE-2026-86950",
        "vendor": "Apple",
        "product": "Multiple Products",
        "ransomware_use": "Unknown",
    }
    fields.update(changes)
    return fields


def release_fields(**changes):
    """A GitHub release, with every field its kind requires."""
    fields = {
        "source_code": "github",
        "source_item_id": "401174143",
        "kind": "release",
        "title": "anthropics/claude-code v2.1.287",
        "url": "https://github.com/anthropics/claude-code/releases/tag/v2.1.287",
        "published_at": datetime(2026, 10, 1, 18, 0, 22, tzinfo=UTC),
        "summary": "## What's changed",
        "collected_at": COLLECTED_AT,
        "raw_file_path": (
            "automated_watch/github_releases_anthropics_claude_code/"
            "2026-10-05T093000Z.json"
        ),
        "repository_name": "anthropics/claude-code",
        "tag_name": "v2.1.287",
        "release_name": "v2.1.287",
    }
    fields.update(changes)
    return fields


def advisory_fields(**changes):
    """A GitHub advisory, with every field its kind requires."""
    fields = {
        "source_code": "github",
        "source_item_id": "GHSA-fjqc-hq36-qh5p",
        "kind": "advisory",
        "title": "LangGraph Checkpoint: Unsafe JSON deserialization",
        "url": "https://github.com/advisories/GHSA-fjqc-hq36-qh5p",
        "published_at": datetime(2026, 6, 25, 18, 25, 42, tzinfo=UTC),
        "collected_at": COLLECTED_AT,
        "raw_file_path": "automated_watch/github_advisories_pip/2026-10-05T093000Z.json",
        "cve": "CVE-2026-48775",
        "package_names": ("langgraph-checkpoint",),
    }
    fields.update(changes)
    return fields


def newsletter_article_fields(**changes):
    """A TLDR article, with every field its kind requires."""
    fields = {
        "source_code": "tldr",
        "source_item_id": "ai/2026-10-07#2",
        "kind": "newsletter_article",
        "title": "Mistral Large 4 (9 minute read)",
        "url": "https://mistral.ai/news/mistral-large-4/",
        "published_at": datetime(2026, 10, 7, tzinfo=UTC),
        "summary": "Mistral Large 4 is a one-trillion-parameter multimodal model.",
        "collected_at": COLLECTED_AT,
        "raw_file_path": "automated_watch/tldr_ai/2026-10-11T153130Z/2026-10-07.html",
        "edition": "ai",
        "rank": 2,
    }
    fields.update(changes)
    return fields


def highlight_fields(**changes):
    """The first highlight of the extract of the fabricated library (tests/conftest.py)."""
    fields = {
        "zotero_key": "ANNOTAA2",
        "text": "A highlighted sentence on the first page.",
        "comment": "A comment on it.",
        "highlighted_at": datetime(2026, 10, 5, 8, 42, 30, tzinfo=UTC),
    }
    fields.update(changes)
    return fields


def zotero_entry_fields(**changes):
    """The first document of the extract of the fabricated library, with every field its
    kind requires."""
    fields = {
        "source_code": "zotero",
        "source_item_id": "AAAAAAA1",
        "kind": "zotero_entry",
        "title": "Prompt injection through tool results",
        "url": "http://arxiv.org/abs/2609.00001",
        "saved_at": datetime(2026, 10, 1, 8, 15, tzinfo=UTC),
        "collected_at": COLLECTED_AT,
        "raw_file_path": "selected_library/zotero/2026-10-05T093000Z.json",
        "item_type": "preprint",
        "arxiv_id": "2609.00001",
        "highlights": (Highlight(**highlight_fields()),),
    }
    fields.update(changes)
    return fields


def test_the_source_codes_are_those_of_the_database():
    seeded_codes = re.findall(r"\('(\w+)',", SEED_SOURCES.read_text())

    assert set(typing.get_args(SourceCode)) == set(seeded_codes)


def test_an_item_keeps_an_absence_as_an_absence():
    item = Item(**advisory_fields(cve=None))

    assert item.authors == ()
    assert item.revised_at is None
    assert item.saved_at is None
    assert item.summary is None
    assert item.cve is None
    assert item.vendor is None
    assert item.product is None
    assert item.ransomware_use is None
    assert item.repository_name is None
    assert item.tag_name is None
    assert item.release_name is None
    assert item.edition is None
    assert item.rank is None
    assert item.item_type is None
    assert item.arxiv_id is None
    assert item.highlights == ()
    assert Item(**item_fields()).package_names == ()


def test_a_paper_and_a_vulnerability_with_their_fields_are_accepted():
    assert Item(**item_fields()).kind == "paper"
    assert Item(**vulnerability_fields()).kind == "vulnerability"


def test_a_release_and_an_advisory_with_their_fields_are_accepted():
    assert Item(**release_fields()).kind == "release"
    assert Item(**release_fields(release_name=None, summary=None)).release_name is None
    assert Item(**advisory_fields()).kind == "advisory"
    assert Item(**advisory_fields(cve=None)).cve is None


@pytest.mark.parametrize(
    "changes",
    [
        {"source_code": "rss"},
        {"source_item_id": ""},
        {"title": ""},
        {"url": "http://arxiv.org/abs/2509.12345"},
        {"url": "arxiv.org/abs/2509.12345"},
        {"published_at": datetime(2026, 10, 1, 18, 0, 22)},
        {"published_at": "2026-10-01T18:00:22Z"},
        {"collected_at": datetime(2026, 10, 5, 9, 30)},
        {"kind": "tweet"},
        {"source_code": "zotero"},
        {"cve": "CVE-2026-48775"},
        {"vendor": "Apple"},
        {"summary": None},
        {"authors": ()},
        {"revised_at": None},
        {"repository_name": "anthropics/claude-code"},
        {"tag_name": "v2.1.287"},
        {"release_name": "v2.1.287"},
        {"package_names": ("langchain",)},
        {"edition": "ai"},
        {"rank": 2},
        {"stars": 3},
    ],
)
def test_an_invalid_item_is_refused(changes):
    with pytest.raises(ValidationError):
        Item(**item_fields(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"source_code": "github"},
        {"cve": "CVE-26-1"},
        {"cve": None},
        {"vendor": None},
        {"vendor": ""},
        {"product": None},
        {"ransomware_use": None},
        {"ransomware_use": "Yes"},
        {"summary": None},
        {"published_at": None},
    ],
)
def test_an_invalid_vulnerability_is_refused(changes):
    with pytest.raises(ValidationError):
        Item(**vulnerability_fields(**changes))


def test_an_item_cannot_be_changed():
    item = Item(**item_fields())

    with pytest.raises(ValidationError):
        item.title = "Another title"


@pytest.mark.parametrize(
    "changes",
    [
        {"source_code": "arxiv"},
        {"repository_name": None},
        {"repository_name": "claude-code"},
        {"tag_name": None},
        {"tag_name": ""},
        {"published_at": None},
        {"cve": "CVE-2026-48775"},
        {"package_names": ("langchain",)},
    ],
)
def test_an_invalid_release_is_refused(changes):
    with pytest.raises(ValidationError):
        Item(**release_fields(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"source_code": "cisa_kev"},
        {"published_at": None},
        {"package_names": ()},
        {"package_names": ("",)},
        {"tag_name": "v2.1.287"},
        {"vendor": "Apple"},
    ],
)
def test_an_invalid_advisory_is_refused(changes):
    with pytest.raises(ValidationError):
        Item(**advisory_fields(**changes))


def test_a_newsletter_article_with_its_fields_is_accepted():
    item = Item(**newsletter_article_fields())

    assert (item.kind, item.edition, item.rank) == ("newsletter_article", "ai", 2)


@pytest.mark.parametrize(
    "changes",
    [
        {"source_code": "arxiv"},
        {"summary": None},
        {"published_at": None},
        {"edition": None},
        {"rank": None},
        # What the CHECK of newsletter_article.edition refuses.
        {"edition": ""},
        {"edition": "AI"},
        {"edition": "a1"},
        {"edition": "ai_old"},
        {"edition": "ai\n"},
        {"edition": "AI ai"},
        # What the CHECK of newsletter_article.rank refuses, and an integer SQLite cannot hold.
        {"rank": 0},
        {"rank": 2**63},
        {"rank": "2"},
        {"rank": True},
        {"repository_name": "anthropics/claude-code"},
        {"cve": "CVE-2026-48775"},
    ],
)
def test_an_invalid_newsletter_article_is_refused(changes):
    with pytest.raises(ValidationError):
        Item(**newsletter_article_fields(**changes))


@pytest.mark.parametrize(
    "url",
    [
        # urlsplit refuses both: etl/normalize.py would raise at the import.
        "https://[x",
        "https://exam\u2100ple.com/a",
    ],
)
def test_a_link_that_cannot_be_split_is_refused(url):
    with pytest.raises(ValidationError) as refusal:
        Item(**newsletter_article_fields(url=url))

    assert f"url cannot be split: {len(url)} characters" in str(refusal.value)


def test_a_link_that_cannot_be_split_is_not_copied_whole_into_the_refusal():
    # urlsplit quotes the host in its error, as written: an escape sequence, 3 000 letters.
    url = "https://a\u2100\x1b[2J" + "b" * 3_000 + "/x"

    with pytest.raises(ValidationError) as refusal:
        Item(**newsletter_article_fields(url=url))

    message = str(refusal.value)
    assert f"url cannot be split: {len(url)} characters" in message
    assert "\x1b" not in message
    assert len(message) < 500


@pytest.mark.parametrize(
    "url",
    [
        # Without its utm_* parameter, the first one is "https://": etl/normalize.py would raise.
        "https://?utm_source=tldrai",
        "https://#part",
        "https:///path",
        "https://:443/path",
        "https://user@/path",
    ],
)
def test_a_link_without_a_host_is_refused(url):
    with pytest.raises(ValidationError) as refusal:
        Item(**newsletter_article_fields(url=url))

    assert f"url without a host: {len(url)} characters" in str(refusal.value)


def test_the_largest_rank_sqlite_holds_is_accepted():
    assert Item(**newsletter_article_fields(rank=2**63 - 1)).rank == 2**63 - 1


def text_of_length(field, length):
    """A text of this length that the format of its field accepts."""
    if field == "edition":
        return "a" * length
    if field == "url":
        return "https://" + "x" * (length - len("https://"))
    if field == "cve":
        return "CVE-2026-" + "1" * (length - len("CVE-2026-"))
    if field == "arxiv_id":
        return "a" * (length - len("/9901001")) + "/9901001"
    return "x" * length


@pytest.mark.parametrize(
    "build_fields, field, maximum",
    [
        (item_fields, "source_item_id", 20),
        (item_fields, "title", 500),
        (item_fields, "summary", 5_000),
        (vulnerability_fields, "cve", 20),
        (vulnerability_fields, "title", 500),
        (vulnerability_fields, "summary", 5_000),
        (vulnerability_fields, "vendor", 200),
        (vulnerability_fields, "product", 500),
        (release_fields, "tag_name", 255),
        (release_fields, "release_name", 255),
        (release_fields, "summary", 125_000),
        (release_fields, "url", 2_000),
        (advisory_fields, "source_item_id", 19),
        (advisory_fields, "cve", 20),
        (advisory_fields, "title", 1_024),
        (advisory_fields, "url", 2_000),
        (newsletter_article_fields, "edition", 20),
        (newsletter_article_fields, "title", 500),
        (newsletter_article_fields, "summary", 5_000),
        (newsletter_article_fields, "url", 2_000),
        (zotero_entry_fields, "item_type", 100),
        (zotero_entry_fields, "title", 1_000),
        (zotero_entry_fields, "url", 2_000),
        (zotero_entry_fields, "arxiv_id", 20),
    ],
)
def test_a_text_is_accepted_up_to_its_maximum_length_and_refused_beyond(
    build_fields, field, maximum
):
    longest = text_of_length(field, maximum)
    assert getattr(Item(**build_fields(**{field: longest})), field) == longest

    with pytest.raises(ValidationError) as refusal:
        Item(**build_fields(**{field: text_of_length(field, maximum + 1)}))

    assert f"{field} too long: {maximum + 1} characters, maximum {maximum}" in str(
        refusal.value
    )


@pytest.mark.parametrize(
    "build_fields, field, maximum",
    [(item_fields, "authors", 1_000), (advisory_fields, "package_names", 100)],
)
def test_a_list_is_accepted_up_to_its_maximum_count_and_refused_beyond(
    build_fields, field, maximum
):
    assert len(getattr(Item(**build_fields(**{field: ("x",) * maximum})), field)) == (
        maximum
    )

    with pytest.raises(ValidationError) as refusal:
        Item(**build_fields(**{field: ("x",) * (maximum + 1)}))

    assert f"{field} too long: {maximum + 1} elements, maximum {maximum}" in str(
        refusal.value
    )


@pytest.mark.parametrize(
    "build_fields, field, maximum",
    [(item_fields, "authors", 200), (advisory_fields, "package_names", 255)],
)
def test_an_element_of_a_list_is_accepted_up_to_its_maximum_length_and_refused_beyond(
    build_fields, field, maximum
):
    longest = "x" * maximum
    assert getattr(Item(**build_fields(**{field: ("x", longest)})), field) == (
        "x",
        longest,
    )

    with pytest.raises(ValidationError) as refusal:
        Item(**build_fields(**{field: ("x", longest + "x")}))

    assert (
        f"an element of {field} too long: {maximum + 1} characters, maximum {maximum}"
        in str(refusal.value)
    )


def test_every_text_too_long_of_an_item_is_named():
    with pytest.raises(ValidationError) as refusal:
        Item(**item_fields(title="x" * 501, summary="x" * 5_001))

    assert "title too long: 501 characters, maximum 500" in str(refusal.value)
    assert "summary too long: 5001 characters, maximum 5000" in str(refusal.value)


def test_a_zotero_entry_with_its_fields_is_accepted():
    item = Item(**zotero_entry_fields())

    assert (item.kind, item.source_item_id, item.arxiv_id) == (
        "zotero_entry",
        "AAAAAAA1",
        "2609.00001",
    )
    assert item.highlights == (Highlight(**highlight_fields()),)


def test_a_zotero_entry_without_url_arxiv_reference_or_highlight_is_accepted():
    item = Item(**zotero_entry_fields(url=None, arxiv_id=None, highlights=()))

    assert (item.url, item.arxiv_id, item.highlights) == (None, None, ())


@pytest.mark.parametrize(
    "changes",
    [
        {"source_code": "arxiv"},
        {"source_item_id": "aaaaaaa1"},
        {"source_item_id": "AAAAAAA"},
        {"source_item_id": "AAAAAAA1X"},
        {"saved_at": None},
        {"item_type": None},
        {"item_type": ""},
        {"arxiv_id": "2609.1"},
        {"arxiv_id": "2609.00001v2"},
        {"url": "ftp://arxiv.org/abs/2609.00001"},
        {"url": "arxiv.org/abs/2609.00001"},
        {"cve": "CVE-2026-48775"},
        {"edition": "ai"},
    ],
)
def test_an_invalid_zotero_entry_is_refused(changes):
    with pytest.raises(ValidationError):
        Item(**zotero_entry_fields(**changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"item_type": "preprint"},
        {"arxiv_id": "2609.00001"},
        {"highlights": (Highlight(**highlight_fields()),)},
    ],
)
def test_the_fields_of_a_zotero_entry_are_refused_on_another_kind(changes):
    with pytest.raises(ValidationError):
        Item(**item_fields(**changes))


OTHER_KINDS_THAN_ZOTERO = [
    item_fields,
    vulnerability_fields,
    release_fields,
    advisory_fields,
    newsletter_article_fields,
]


@pytest.mark.parametrize("build_fields", OTHER_KINDS_THAN_ZOTERO)
def test_only_a_zotero_entry_may_have_no_url(build_fields):
    with pytest.raises(ValidationError) as refusal:
        Item(**build_fields(url=None))

    assert "without url" in str(refusal.value)


@pytest.mark.parametrize("build_fields", OTHER_KINDS_THAN_ZOTERO)
def test_only_a_zotero_entry_may_have_an_http_url(build_fields):
    url = build_fields()["url"].replace("https://", "http://", 1)

    with pytest.raises(ValidationError) as refusal:
        Item(**build_fields(url=url))

    assert "url not https" in str(refusal.value)


@pytest.mark.parametrize("field, maximum", [("text", 10_000), ("comment", 10_000)])
def test_a_highlight_text_is_accepted_up_to_its_maximum_length_and_refused_beyond(
    field, maximum
):
    assert getattr(Highlight(**highlight_fields(**{field: "x" * maximum})), field) == (
        "x" * maximum
    )

    with pytest.raises(ValidationError):
        Highlight(**highlight_fields(**{field: "x" * (maximum + 1)}))


@pytest.mark.parametrize(
    "changes",
    [
        {"zotero_key": "annotaa2"},
        {"zotero_key": "ANNOTAA"},
        {"highlighted_at": datetime(2026, 10, 5, 8, 42, 30)},
        {"highlighted_at": "2026-10-05 08:42:30"},
        {"page_label": "1"},
    ],
)
def test_an_invalid_highlight_is_refused(changes):
    with pytest.raises(ValidationError):
        Highlight(**highlight_fields(**changes))


def test_a_highlight_without_comment_is_accepted():
    assert Highlight(**highlight_fields(comment=None)).comment is None


def test_a_highlight_without_text_is_accepted_with_its_comment():
    assert Highlight(**highlight_fields(text=None)).text is None


def test_a_highlight_without_text_or_comment_is_refused():
    with pytest.raises(ValidationError):
        Highlight(**highlight_fields(text=None, comment=None))


# The new form, and the form of before 2007: archive, optional subject class, 7 digits.
@pytest.mark.parametrize(
    "arxiv_id",
    ["2609.00001", "0704.0001", "hep-th/9901001", "math.GT/0309136", "cs/0601001"],
)
def test_an_arxiv_reference_of_either_form_is_accepted(arxiv_id):
    assert Item(**zotero_entry_fields(arxiv_id=arxiv_id)).arxiv_id == arxiv_id


@pytest.mark.parametrize(
    "arxiv_id",
    [
        "\uff12\uff16\uff10\uff19.00001",
        "hep-th/990100\u0661",
        "HEP-TH/9901001",
        "hep-th/990100",
    ],
)
def test_an_arxiv_reference_with_other_than_ascii_digits_or_its_form_is_refused(
    arxiv_id,
):
    with pytest.raises(ValidationError):
        Item(**zotero_entry_fields(arxiv_id=arxiv_id))
