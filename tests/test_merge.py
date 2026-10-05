from datetime import UTC, datetime, timedelta, timezone

from k_b.items import Item
from k_b.merge import merge_items

FIRST_COLLECTION = datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
SECOND_COLLECTION = datetime(2026, 10, 6, 9, 30, tzinfo=UTC)


def make_item(**changes):
    fields = {
        "source_code": "github",
        "source_item_id": "GHSA-fjqc-hq36-qh5p",
        "title": "Path traversal in langchain",
        "url": "https://github.com/advisories/GHSA-fjqc-hq36-qh5p",
        "collected_at": FIRST_COLLECTION,
        "raw_file_path": "automation/github_advisories_pip/2026-10-05T093000Z.json",
    }
    fields.update(changes)
    return Item(**fields)


def make_paper(revised_at, collected_at, title="A paper"):
    return make_item(
        source_code="arxiv",
        source_item_id="2509.12345",
        title=title,
        url="https://arxiv.org/abs/2509.12345",
        authors=("Ada Lovelace",),
        published_at=datetime(2025, 9, 15, 17, 0, tzinfo=UTC),
        revised_at=revised_at,
        collected_at=collected_at,
    )


def test_distinct_items_are_all_kept_in_order():
    first = make_item()
    second = make_item(
        source_item_id="GHSA-gr75-jv2w-4656",
        url="https://github.com/advisories/GHSA-gr75-jv2w-4656",
    )

    merged = merge_items([first, second])

    assert merged.items == [first, second]
    assert merged.discards == []


def test_utm_parameters_are_removed_and_the_others_kept_in_order():
    item = make_item(
        source_code="tldr",
        source_item_id="article",
        url="https://example.com/post?utm_source=tldrai&id=7&utm_medium=newsletter&page=2#part",
    )

    assert merge_items([item]).items[0].url == "https://example.com/post?id=7&page=2#part"


def test_a_query_made_only_of_utm_parameters_disappears():
    item = make_item(
        source_code="tldr",
        source_item_id="article",
        url="https://example.com/post?utm_source=tldrai",
    )

    assert merge_items([item]).items[0].url == "https://example.com/post"


def test_dates_are_brought_to_utc():
    paris = timezone(timedelta(hours=2))
    item = make_item(published_at=datetime(2026, 10, 1, 20, 0, 22, tzinfo=paris))

    published_at = merge_items([item]).items[0].published_at

    assert published_at == datetime(2026, 10, 1, 18, 0, 22, tzinfo=UTC)
    assert published_at.tzinfo == UTC


def test_the_same_source_item_seen_again_is_discarded_and_the_first_collection_kept():
    first = make_item()
    again = make_item(
        collected_at=SECOND_COLLECTION,
        raw_file_path="automation/github_advisories_pip/2026-10-06T093000Z.json",
    )

    merged = merge_items([first, again])

    assert merged.items == [first]
    assert [(discard.rule, discard.item, discard.kept_url) for discard in merged.discards] == [
        ("same_source_id", again, first.url)
    ]


def test_the_same_url_from_another_source_is_discarded():
    first = make_item(source_code="tldr", source_item_id="article", url="https://example.com/post")
    same_url = make_item(
        source_code="clipper", source_item_id="post.md", url="https://example.com/post?utm_source=x"
    )

    merged = merge_items([first, same_url])

    assert [item.source_code for item in merged.items] == ["tldr"]
    assert [discard.rule for discard in merged.discards] == ["same_url"]


def test_the_same_cve_from_another_source_is_kept_as_a_second_item():
    from_cisa = make_item(
        source_code="cisa_kev",
        source_item_id="CVE-2026-48775",
        url="https://nvd.nist.gov/vuln/detail/CVE-2026-48775",
        cve="CVE-2026-48775",
        is_vulnerability=True,
    )
    from_github = make_item(cve="CVE-2026-48775", is_vulnerability=True)

    merged = merge_items([from_cisa, from_github])

    assert merged.items == [from_cisa, from_github]
    assert merged.discards == []


def test_the_same_cve_within_one_source_is_discarded_and_the_first_seen_kept():
    first = make_item(cve="CVE-2026-48775", is_vulnerability=True)
    same_cve = make_item(
        source_item_id="GHSA-gr75-jv2w-4656",
        url="https://github.com/advisories/GHSA-gr75-jv2w-4656",
        cve="CVE-2026-48775",
        is_vulnerability=True,
    )

    merged = merge_items([first, same_cve])

    assert merged.items == [first]
    assert [(discard.rule, discard.item, discard.kept_url) for discard in merged.discards] == [
        ("same_cve", same_cve, first.url)
    ]


def test_items_without_cve_are_not_duplicates_of_each_other():
    first = make_item()
    second = make_item(
        source_item_id="GHSA-gr75-jv2w-4656",
        url="https://github.com/advisories/GHSA-gr75-jv2w-4656",
    )

    assert len(merge_items([first, second]).items) == 2


def test_a_newer_arxiv_revision_replaces_the_kept_paper_in_place():
    other = make_item()
    version_1 = make_paper(datetime(2025, 9, 15, 17, 0, tzinfo=UTC), FIRST_COLLECTION)
    version_2 = make_paper(
        datetime(2025, 9, 20, 12, 0, tzinfo=UTC), SECOND_COLLECTION, title="A paper, revised"
    )

    merged = merge_items([version_1, other, version_2])

    assert merged.items == [version_2, other]
    assert [(discard.rule, discard.item, discard.kept_url) for discard in merged.discards] == [
        ("arxiv_revision", version_1, version_2.url)
    ]


def test_an_arxiv_paper_seen_again_without_revision_keeps_the_first_collection():
    first = make_paper(datetime(2025, 9, 15, 17, 0, tzinfo=UTC), FIRST_COLLECTION)
    again = make_paper(datetime(2025, 9, 15, 17, 0, tzinfo=UTC), SECOND_COLLECTION)

    merged = merge_items([first, again])

    assert merged.items == [first]
    assert [discard.rule for discard in merged.discards] == ["same_source_id"]
