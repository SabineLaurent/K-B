"""The twin of the sheet of a digest (#560): one closed schema for kb digest, which writes it, and
for the data API, which reads it again."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from k_b.core.config import (
    GITHUB_TRACKED_REPOSITORIES,
    ITEMS_PER_CLAIM,
    MAX_CLAIMS,
    MAX_ITEMS_PER_DIGEST,
    TEXT_CHARS,
)
from k_b.items import (
    MAX_DIGEST_SOURCE_TITLE_CHARS,
    MAX_DIGEST_SOURCE_URL_CHARS,
    MAX_LENGTH_BY_KIND,
    DigestProduction,
)

ZERO_WIDTH_JOINER = chr(0x200D)
RIGHT_TO_LEFT_OVERRIDE = chr(0x202E)
LONE_SURROGATE = chr(0xD800)
RELEASE_SOURCE = {
    "item_id": 6,
    "title": "Claude Code 2.1.287",
    "url": "https://github.com/anthropics/claude-code/releases/tag/v2.1.287",
}
PAPER_SOURCE = {
    "item_id": 1,
    "title": "Resource-Optimized and Energy-Aware Agentic AI Framework",
    "url": "https://arxiv.org/abs/2609.31282",
}
TWIN = {
    "subject": "agent_tools",
    "since": "2026-10-18T16:30:00Z",
    "until": "2026-10-21T16:30:00Z",
    "model": "gpt-6-luna",
    "items_capped": False,
    "capped_kind": None,
    "covered_after": None,
    "outcome": "written",
    "claims": [
        {"text": "Claude Code publie la version v2.1.287.", "item_ids": [6]},
        {"text": "Un cadre d'agents protège la chaîne logicielle.", "item_ids": [1, 6]},
    ],
    "sources": [RELEASE_SOURCE, PAPER_SOURCE],
}
EMPTY_TWIN = {**TWIN, "outcome": "no_item", "claims": [], "sources": []}
CAPPED = {
    "items_capped": True,
    "capped_kind": "newsletter_article",
    "covered_after": "2026-10-19T00:00:00Z",
}


def read_twin(twin):
    return DigestProduction.model_validate_json(json.dumps(twin))


def with_source(**changes):
    return {
        **TWIN,
        "claims": [{"text": "Une affirmation.", "item_ids": [6]}],
        "sources": [{**RELEASE_SOURCE, **changes}],
    }


def with_claim(**changes):
    return {
        **TWIN,
        "claims": [{"text": "Une affirmation.", "item_ids": [6], **changes}],
        "sources": [RELEASE_SOURCE],
    }


def list_sources(count):
    return [
        {"item_id": number, "title": f"Titre {number}", "url": None}
        for number in range(1, count + 1)
    ]


def test_a_twin_as_kb_writes_it_is_read_again():
    production = read_twin(TWIN)

    assert production.until == datetime(2026, 10, 21, 16, 30, tzinfo=UTC)
    assert json.loads(production.model_dump_json()) == TWIN


@pytest.mark.parametrize(
    "twin",
    [
        EMPTY_TWIN,
        {**EMPTY_TWIN, "outcome": "no_claim"},
        {**TWIN, **CAPPED},
        {**TWIN, "since": TWIN["until"]},
        with_source(url=None),
        with_source(title=f"👩{ZERO_WIDTH_JOINER}💻 <b>as text</b> | # [x](y)"),
        with_source(title="a" * MAX_DIGEST_SOURCE_TITLE_CHARS),
        with_source(
            url="https://example.org/" + "a" * (MAX_DIGEST_SOURCE_URL_CHARS - 20)
        ),
        with_claim(text="a" * TEXT_CHARS[1]),
    ],
)
def test_a_twin_within_its_bounds_is_read(twin):
    assert json.loads(read_twin(twin).model_dump_json()) == twin


def test_a_twin_holds_a_whole_digest():
    sources = list_sources(MAX_ITEMS_PER_DIGEST)
    twin = {
        **TWIN,
        "claims": [
            {
                "text": "Une affirmation.",
                "item_ids": [
                    source["item_id"]
                    for source in sources[number::MAX_CLAIMS][: ITEMS_PER_CLAIM[1]]
                ],
            }
            for number in range(MAX_CLAIMS)
        ],
        "sources": sources,
    }

    assert len(read_twin(twin).sources) == MAX_ITEMS_PER_DIGEST


def test_the_bound_of_a_title_holds_the_longest_title_of_each_kind_of_the_watch():
    """The base bounds each title (MAX_LENGTH_BY_KIND); a release joins its repository, one of
    the list, and its name or its tag (database/reading.py)."""
    longest_release = (
        max(len(repository.name) for repository in GITHUB_TRACKED_REPOSITORIES)
        + 1
        + max(
            MAX_LENGTH_BY_KIND["release"]["release_name"],
            MAX_LENGTH_BY_KIND["release"]["tag_name"],
        )
    )
    longest_titles = [
        MAX_LENGTH_BY_KIND[kind]["title"]
        for kind in ("paper", "vulnerability", "advisory", "newsletter_article")
    ]

    assert max([longest_release, *longest_titles]) <= MAX_DIGEST_SOURCE_TITLE_CHARS


def test_the_bound_of_a_url_holds_the_longest_url_of_each_kind_of_the_watch():
    longest_urls = [
        MAX_LENGTH_BY_KIND[kind]["url"]
        for kind in ("release", "advisory", "newsletter_article")
    ]

    assert max(longest_urls) <= MAX_DIGEST_SOURCE_URL_CHARS


@pytest.mark.parametrize(
    "twin",
    [
        {**TWIN, "request_id": "1b4e28ba-2fa1-4d2e-9b5c-6c8e1f0a7d3e"},
        {**TWIN, "subject": "Agent-Tools"},
        {**TWIN, "subject": "../tops"},
        {**TWIN, "subject": "a" * 65},
        {**TWIN, "model": "gpt 6"},
        {**TWIN, "model": "gpt-6\n"},
        {**TWIN, "since": "2026-10-18T16:30:00"},
        {**TWIN, "until": "1760000000"},
        {**TWIN, "since": "2026-10-22T16:30:00Z"},
        {**TWIN, "items_capped": "false"},
        {**TWIN, "items_capped": True},
        {**TWIN, "capped_kind": "newsletter_article"},
        {**TWIN, **CAPPED, "covered_after": None},
        {**TWIN, **CAPPED, "capped_kind": "clip_kind"},
        {**TWIN, "outcome": "failed"},
        {**TWIN, "outcome": "no_claim"},
        {**EMPTY_TWIN, "outcome": "written"},
        {**EMPTY_TWIN, "sources": [RELEASE_SOURCE]},
        {**TWIN, "sources": [RELEASE_SOURCE]},
        {
            **TWIN,
            "sources": [RELEASE_SOURCE, PAPER_SOURCE, {**PAPER_SOURCE, "item_id": 7}],
        },
        {**TWIN, "sources": [RELEASE_SOURCE, PAPER_SOURCE, RELEASE_SOURCE]},
        with_claim(item_ids=[6, 6]),
        with_claim(item_ids=[]),
        with_claim(item_ids=[6] * (ITEMS_PER_CLAIM[1] + 1)),
        with_claim(text=""),
        with_claim(text="a" * (TEXT_CHARS[1] + 1)),
        with_claim(text=f"Un texte {RIGHT_TO_LEFT_OVERRIDE} caché."),
        with_claim(text="Deux\nlignes."),
        with_claim(fact="une donnée en plus"),
        with_source(item_id=0),
        with_source(item_id="6"),
        with_source(title=f"Un titre {RIGHT_TO_LEFT_OVERRIDE} caché"),
        with_source(title=f"Un titre {LONE_SURROGATE}"),
        with_source(title="a" * (MAX_DIGEST_SOURCE_TITLE_CHARS + 1)),
        with_source(url="javascript:alert(1)"),
        with_source(url="https://example.org/a b"),
        with_source(url="https://example.org/a::b"),
        with_source(url="https://example.org/%E2%80%AE"),
        with_source(url="https://example.org/" + "a" * MAX_DIGEST_SOURCE_URL_CHARS),
        with_source(kind="release"),
        {
            **TWIN,
            "claims": [{"text": "Une affirmation.", "item_ids": [1]}]
            * (MAX_CLAIMS + 1),
            "sources": [PAPER_SOURCE],
        },
        {**TWIN, "sources": list_sources(MAX_ITEMS_PER_DIGEST + 1)},
    ],
)
def test_a_twin_out_of_the_schema_is_refused(twin):
    with pytest.raises(ValidationError):
        read_twin(twin)
