"""The GitHub repositories K-B watches, and the packages each one publishes.

The list and the reasons for each repository are in docs/sources.md. A repository gives its
releases; its packages give its security advisories.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class TrackedRepository:
    name: str
    ecosystem: Literal["pip", "npm"]
    # Only the main packages: integrations are added when they are used.
    packages: tuple[str, ...]


TRACKED_REPOSITORIES = (
    TrackedRepository(
        "langchain-ai/langchain",
        "pip",
        ("langchain", "langchain-core", "langchain-classic", "langchain-text-splitters"),
    ),
    TrackedRepository("langchain-ai/langgraph", "pip", ("langgraph", "langgraph-checkpoint")),
    TrackedRepository("run-llama/llama_index", "pip", ("llama-index", "llama-index-core")),
    TrackedRepository("anthropics/claude-code", "npm", ("@anthropic-ai/claude-code",)),
)


def list_packages_by_ecosystem(
    repositories: tuple[TrackedRepository, ...],
) -> dict[str, tuple[str, ...]]:
    packages_by_ecosystem: dict[str, tuple[str, ...]] = {}
    for repository in repositories:
        known_packages = packages_by_ecosystem.get(repository.ecosystem, ())
        packages_by_ecosystem[repository.ecosystem] = known_packages + repository.packages
    return packages_by_ecosystem
