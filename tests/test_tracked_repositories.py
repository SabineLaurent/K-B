from k_b.tracked_repositories import (
    TRACKED_REPOSITORIES,
    TrackedRepository,
    list_packages_by_ecosystem,
)


def test_packages_are_grouped_by_ecosystem_in_the_order_of_the_repositories():
    repositories = (
        TrackedRepository("owner/first", "pip", ("first", "first-core")),
        TrackedRepository("owner/tool", "npm", ("@owner/tool",)),
        TrackedRepository("owner/second", "pip", ("second",)),
    )

    assert list_packages_by_ecosystem(repositories) == {
        "pip": ("first", "first-core", "second"),
        "npm": ("@owner/tool",),
    }


def test_the_tracked_repositories_are_those_of_docs_sources():
    assert [repository.name for repository in TRACKED_REPOSITORIES] == [
        "langchain-ai/langchain",
        "langchain-ai/langgraph",
        "run-llama/llama_index",
        "anthropics/claude-code",
    ]
    assert list_packages_by_ecosystem(TRACKED_REPOSITORIES)["npm"] == (
        "@anthropic-ai/claude-code",
    )
