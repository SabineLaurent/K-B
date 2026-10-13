from k_b.etl.source_contract import SourceKind, find_source_kind, list_sources

RELEASES = SourceKind("github_releases", (), None)
STARRED = SourceKind("github_most_starred", (), None)
KINDS = (RELEASES, STARRED)


def test_a_folder_named_after_a_prefix_belongs_to_its_kind():
    assert find_source_kind("github_most_starred", KINDS) is STARRED


def test_a_folder_starting_with_a_prefix_and_an_underscore_belongs_to_its_kind():
    assert find_source_kind("github_releases_someone_untracked", KINDS) is RELEASES


def test_a_folder_of_no_kind_has_none():
    assert find_source_kind("github_releasesx", KINDS) is None
    assert find_source_kind("unknown", KINDS) is None


def test_the_sources_are_listed_kind_after_kind():
    first, second, third = object(), object(), object()
    kinds = (
        SourceKind("a", (first, second), None),  # type: ignore[arg-type]
        SourceKind("b", (third,), None),  # type: ignore[arg-type]
    )

    assert list_sources(kinds) == [first, second, third]
