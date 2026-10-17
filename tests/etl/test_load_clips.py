"""The import of the clips: a news feed, the first version of a URL is kept (decision of Sabine
of 2026-10-17). Each clip is written as the collection writes it, a page of a collection folder
of raw/selected_library/clipping/, from the fixtures of tests/fixtures/clipping/."""

from pathlib import Path

import pytest
from test_load import dump_database, fetch_rows, read_discards, read_log, run_import

from k_b.database.creation import create_database

FIXTURES_DIR = Path(__file__).parents[1] / "fixtures" / "clipping"
ARTICLE = "article_with_author.md"
PAGE_WITHOUT_AUTHOR = "page_without_author_or_date.md"
ARTICLE_URL = (
    "https://medium.com/skillstuff/"
    "7-coding-patterns-i-stole-from-senior-engineers-c95f757e52a6"
)
FIRST = "2026-10-17T093000Z"
SECOND = "2026-10-18T093000Z"
FIRST_AT = "2026-10-17T09:30:00Z"
CLIPPING_DIR = "selected_library/clipping"
CLIP_QUERY = (
    "SELECT url, title, body, saved_at, published_at, raw_file_path"
    " FROM clip JOIN item ON item.id = clip.item_id"
    " JOIN raw_data ON raw_data.id = item.raw_data_id ORDER BY url"
)


@pytest.fixture
def data_dir(tmp_path):
    create_database(tmp_path / "k-b.sqlite")
    return tmp_path


def fixture_text(name):
    return (FIXTURES_DIR / name).read_text()


def write_clip(data_dir, collection, page_name, text):
    """A clip copied by a collection, under its page name."""
    folder = data_dir / "raw" / CLIPPING_DIR / collection
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{page_name}.md").write_text(text)
    return f"{CLIPPING_DIR}/{collection}/{page_name}.md"


def test_a_clip_gives_an_item_and_its_clip(data_dir):
    raw_file_path = write_clip(data_dir, FIRST, "a1", fixture_text(ARTICLE))

    run_import(data_dir)

    assert fetch_rows(data_dir, CLIP_QUERY) == [
        (
            ARTICLE_URL,
            "7 Coding Patterns I Stole From Senior Engineers",
            (
                "## Most developers do not become better simply by learning more syntax.\n\n"
                "Most junior developers think senior engineers know more tricks.\n\n"
                "They usually do not.\n"
            ),
            "2026-09-17T00:00:00Z",
            "2026-06-08T00:00:00Z",
            raw_file_path,
        )
    ]
    assert fetch_rows(
        data_dir,
        "SELECT source.source_code, source.acquisition_mode, item.kind FROM item"
        " JOIN raw_data ON raw_data.id = item.raw_data_id"
        " JOIN source ON source.id = raw_data.source_id",
    ) == [("clipper", "library", "clip")]
    assert read_log(data_dir) == []


def test_a_clip_without_publication_date_has_none(data_dir):
    write_clip(data_dir, FIRST, "b2", fixture_text(PAGE_WITHOUT_AUTHOR))

    run_import(data_dir)

    assert fetch_rows(data_dir, "SELECT published_at FROM clip") == [(None,)]


def test_a_clip_of_a_url_already_seen_keeps_its_first_version(data_dir):
    first_path = write_clip(data_dir, FIRST, "a1", fixture_text(ARTICLE))
    run_import(data_dir)
    changed = fixture_text(ARTICLE).replace("They usually do not.", "Changed.")
    second_path = write_clip(data_dir, SECOND, "a1", changed)

    run_import(data_dir)

    assert [row[5] for row in fetch_rows(data_dir, CLIP_QUERY)] == [first_path]
    assert "They usually do not." in fetch_rows(data_dir, "SELECT body FROM clip")[0][0]
    assert read_discards(data_dir) == [
        {
            "kind": "discard",
            "rule": "already_seen",
            "source_code": "clipper",
            "source_item_id": ARTICLE_URL,
            "raw_file_path": second_path,
            "compared_with_collected_at": FIRST_AT,
        }
    ]


def test_two_urls_that_differ_by_their_utm_parameters_are_one_clip(data_dir):
    write_clip(data_dir, FIRST, "a1", fixture_text(ARTICLE))
    with_tracking = fixture_text(ARTICLE).replace(
        f'source: "{ARTICLE_URL}"', f'source: "{ARTICLE_URL}?utm_source=newsletter"'
    )
    write_clip(data_dir, FIRST, "a2", with_tracking)

    run_import(data_dir)

    assert fetch_rows(data_dir, "SELECT url FROM clip") == [(ARTICLE_URL,)]
    assert [discard["rule"] for discard in read_discards(data_dir)] == ["already_seen"]


def test_two_urls_are_two_clips_even_for_the_same_article(data_dir):
    """The limit of the key (ADR, "Collecte : clips"): no content fingerprint."""
    write_clip(data_dir, FIRST, "a1", fixture_text(ARTICLE))
    other_url = fixture_text(ARTICLE).replace(
        f'source: "{ARTICLE_URL}"', 'source: "https://example.com/the-same-article"'
    )
    write_clip(data_dir, FIRST, "a2", other_url)

    run_import(data_dir)

    assert fetch_rows(data_dir, "SELECT count(*), count(DISTINCT body) FROM clip") == [
        (2, 1)
    ]
    assert read_discards(data_dir) == []


def test_of_two_files_of_one_url_in_a_collection_the_first_page_name_is_kept(data_dir):
    first_path = write_clip(data_dir, FIRST, "a1", fixture_text(ARTICLE))
    write_clip(data_dir, FIRST, "b2", fixture_text(ARTICLE).replace("do not", "never"))

    run_import(data_dir)

    assert [row[5] for row in fetch_rows(data_dir, CLIP_QUERY)] == [first_path]


def test_a_refused_clip_is_logged_by_its_field_without_its_title(data_dir):
    refused = fixture_text(ARTICLE).replace("created: 2026-09-17", "created: tomorrow")
    raw_file_path = write_clip(data_dir, FIRST, "a1", refused)
    write_clip(data_dir, FIRST, "b2", fixture_text(PAGE_WITHOUT_AUTHOR))

    run_import(data_dir)

    (rejection,) = read_log(data_dir)
    assert rejection["raw_file_path"] == raw_file_path
    assert "created" in rejection["reason"]
    assert "Coding Patterns" not in rejection["reason"]
    assert "Jane Doe" not in rejection["reason"]
    assert fetch_rows(data_dir, "SELECT count(*) FROM clip") == [(1,)]


def test_an_unreadable_clip_is_rejected_at_each_import_and_not_registered(data_dir):
    raw_file_path = write_clip(data_dir, FIRST, "a1", "Coding Patterns, no frontmatter")

    run_import(data_dir)
    run_import(data_dir)

    assert read_log(data_dir) == [
        {
            "kind": "rejection",
            "raw_file_path": raw_file_path,
            "reason": "ValueError: clip without frontmatter",
        }
    ]
    assert fetch_rows(data_dir, "SELECT count(*) FROM raw_data") == [(0,)]


def test_a_rebuilt_base_is_the_same(data_dir, tmp_path):
    write_clip(data_dir, FIRST, "a1", fixture_text(ARTICLE))
    write_clip(data_dir, SECOND, "a1", fixture_text(ARTICLE).replace("do not", "never"))
    write_clip(data_dir, SECOND, "b2", fixture_text(PAGE_WITHOUT_AUTHOR))
    run_import(data_dir)
    first_dump = dump_database(data_dir)

    (data_dir / "k-b.sqlite").unlink()
    create_database(data_dir / "k-b.sqlite")
    run_import(data_dir)

    assert dump_database(data_dir) == first_dump
