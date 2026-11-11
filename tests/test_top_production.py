"""The twin of the sheet of a top (#559): one closed schema for kb write-tops, which writes it,
and for the data API, which reads it again."""

import json
from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from k_b.core.config import GITHUB_RANKING_SIZE
from k_b.etl.source_kinds import TOPS
from k_b.items import MAX_TOP_DESCRIPTION_CHARS, TopName, TopProduction

ZERO_WIDTH_JOINER = chr(0x200D)
RIGHT_TO_LEFT_OVERRIDE = chr(0x202E)
LONE_SURROGATE = chr(0xD800)
REPOSITORY = {
    "rank": 1,
    "repository_name": "codecrafters-io/build-your-own-x",
    "url": "https://github.com/codecrafters-io/build-your-own-x",
    "description": "Master programming by recreating your favorite technologies.",
    "description_truncated": False,
    "count": 551156,
}
TWIN = {
    "top": "most_starred",
    "collected_at": "2026-10-05T09:30:00Z",
    "repositories": [REPOSITORY],
}


def read_twin(twin):
    return TopProduction.model_validate_json(json.dumps(twin))


def with_repository(**changes):
    return {**TWIN, "repositories": [{**REPOSITORY, **changes}]}


def list_repositories(count):
    return [{**REPOSITORY, "rank": rank} for rank in range(1, count + 1)]


def test_a_twin_as_kb_writes_it_is_read_again():
    production = read_twin(TWIN)

    assert production.collected_at == datetime(2026, 10, 5, 9, 30, tzinfo=UTC)
    assert json.loads(production.model_dump_json()) == TWIN


@pytest.mark.parametrize(
    "description",
    [
        None,
        "",
        f"👩{ZERO_WIDTH_JOINER}💻 <b>as text</b> | # [x](y)",
        "a" * MAX_TOP_DESCRIPTION_CHARS,
    ],
)
def test_an_absent_empty_joined_or_longest_description_is_read(description):
    repository = read_twin(with_repository(description=description)).repositories[0]

    assert repository.description == description


def test_a_twin_holds_a_whole_ranking():
    twin = {**TWIN, "repositories": list_repositories(GITHUB_RANKING_SIZE)}

    assert len(read_twin(twin).repositories) == GITHUB_RANKING_SIZE


def test_the_names_of_the_tops_are_those_of_their_twins():
    """The data API reads the twins of a top in the folder named after it."""
    assert tuple(top.name for top in TOPS) == get_args(TopName)


@pytest.mark.parametrize(
    "twin",
    [
        pytest.param({**TWIN, "rank_count": 1}, id="field out of the schema"),
        pytest.param({**TWIN, "top": "most_watched"}, id="top unknown"),
        pytest.param({**TWIN, "collected_at": "1760000000"}, id="Unix time as text"),
        pytest.param({**TWIN, "collected_at": 1760000000}, id="Unix time"),
        pytest.param({**TWIN, "collected_at": "2026-10-05T09:30:00"}, id="no zone"),
        pytest.param({**TWIN, "collected_at": "2026-10-05"}, id="a day"),
        pytest.param(
            {**TWIN, "repositories": list_repositories(GITHUB_RANKING_SIZE + 1)},
            id="longer than a ranking",
        ),
        pytest.param(
            {**TWIN, "repositories": [REPOSITORY, REPOSITORY]}, id="rank repeated"
        ),
        pytest.param(with_repository(rank=2), id="rank not from 1"),
        pytest.param(with_repository(rank=1.0), id="rank not an integer"),
        pytest.param(with_repository(stars=1), id="field of a repository unknown"),
        pytest.param(
            with_repository(url="https://github.com/someone/else"),
            id="url of another repository",
        ),
        pytest.param(
            with_repository(url="http://github.com/codecrafters-io/build-your-own-x"),
            id="url in http",
        ),
        pytest.param(
            with_repository(
                repository_name="codecrafters-io/..",
                url="https://github.com/codecrafters-io/..",
            ),
            id="name climbing",
        ),
        pytest.param(
            with_repository(repository_name="a/b c", url="https://github.com/a/b c"),
            id="name with a space",
        ),
        pytest.param(
            with_repository(
                repository_name="a/" + "b" * 255,
                url="https://github.com/a/" + "b" * 255,
            ),
            id="name too long",
        ),
        pytest.param(with_repository(count=-1), id="count negative"),
        pytest.param(with_repository(count=True), id="count a boolean"),
        pytest.param(with_repository(count=2**63), id="count beyond 64 bits"),
        pytest.param(
            with_repository(description_truncated="false"), id="truncated as text"
        ),
        pytest.param(
            with_repository(description="a" * (MAX_TOP_DESCRIPTION_CHARS + 1)),
            id="description too long",
        ),
        pytest.param(with_repository(description="a\nb"), id="control in a text"),
        pytest.param(
            with_repository(description=f"a{RIGHT_TO_LEFT_OVERRIDE}b"),
            id="format character in a text",
        ),
        pytest.param(
            with_repository(description=f"a{LONE_SURROGATE}b"),
            id="lone surrogate in a text",
        ),
    ],
)
def test_a_twin_out_of_the_schema_is_refused(twin):
    with pytest.raises(ValidationError):
        read_twin(twin)
