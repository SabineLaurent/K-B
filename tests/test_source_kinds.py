from k_b.source import find_source_kind, list_sources
from k_b.source_kinds import SOURCE_KINDS


def test_the_sources_are_collected_in_the_order_of_2026_10_06():
    assert [source.name for source in list_sources(SOURCE_KINDS)] == [
        "cisa_kev",
        "github_releases_langchain_ai_langchain",
        "github_releases_langchain_ai_langgraph",
        "github_releases_run_llama_llama_index",
        "github_releases_anthropics_claude_code",
        "github_advisories_pip",
        "github_advisories_npm",
        "github_most_starred",
        "arxiv",
        "tldr_ai",
        "tldr_infosec",
        "tldr_dev",
    ]


def test_each_source_belongs_to_its_own_kind():
    for kind in SOURCE_KINDS:
        for source in kind.sources:
            assert find_source_kind(source.name, SOURCE_KINDS) is kind


def test_no_folder_prefix_covers_another():
    prefixes = [kind.folder_prefix for kind in SOURCE_KINDS]
    for prefix in prefixes:
        for other in prefixes:
            if other is not prefix:
                assert other != prefix
                assert not other.startswith(prefix + "_")
