"""The GitHub repositories K-B watches, the packages each one publishes, and what a repository
name is.

The list and the reasons for each repository are in docs/sources.md. A repository gives its
releases; its packages give its security advisories.
"""

import re

from k_b.config import TrackedRepository

OWNER_SLASH_NAME = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


TRACKED_REPOSITORIES = (
    TrackedRepository(
        "langchain-ai/langchain",
        "pip",
        ("langchain", "langchain-core", "langchain-text-splitters"),
    ),
    TrackedRepository(
        "langchain-ai/langgraph", "pip", ("langgraph", "langgraph-checkpoint")
    ),
    TrackedRepository(
        "run-llama/llama_index", "pip", ("llama-index", "llama-index-core")
    ),
    TrackedRepository("anthropics/claude-code", "npm", ("@anthropic-ai/claude-code",)),
)


def list_packages_by_ecosystem(
    repositories: tuple[TrackedRepository, ...],
) -> dict[str, tuple[str, ...]]:
    packages_by_ecosystem: dict[str, tuple[str, ...]] = {}
    for repository in repositories:
        known_packages = packages_by_ecosystem.get(repository.ecosystem, ())
        packages_by_ecosystem[repository.ecosystem] = (
            known_packages + repository.packages
        )
    return packages_by_ecosystem


def is_repository_name(text: str) -> bool:
    """owner/name, where neither part is `.` nor contains `..`: the name goes into paths."""
    return (
        OWNER_SLASH_NAME.fullmatch(text) is not None
        and ".." not in text
        and "." not in text.split("/")
    )
