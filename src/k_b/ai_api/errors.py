"""The errors of the AI API that the model, the data API or GitHub gives; 502, 503 and 504 say the
failure upstream, as a gateway (RFC 9110, § 15.6)."""

from collections.abc import Iterable
from itertools import groupby
from typing import Any, get_args

from k_b.ai_api.connectors.data_api_client import DataApiState
from k_b.ai_api.connectors.github_client import GithubState
from k_b.ai_api.connectors.llm_client import LlmFailure
from k_b.core.api_errors import API_ERROR_RESPONSES, ApiError, ErrorSchema

type UpstreamState = LlmFailure | DataApiState | GithubState

# The states of a reading or of a classification that fails the request; a writing that fails
# names its subject in the response instead.
STATUS_BY_STATE: dict[UpstreamState, int] = {
    "data_api_invalid_response": 502,
    "data_api_timeout": 504,
    "data_api_unauthorized": 502,
    "data_api_unavailable": 502,
    "github_forbidden": 502,
    "github_invalid_response": 502,
    "github_rate_limited": 503,
    "github_timeout": 504,
    "github_unauthorized": 502,
    "github_unavailable": 502,
    "llm_content_filtered": 502,
    "llm_invalid_output": 502,
    "llm_rate_limited": 503,
    "llm_timeout": 504,
    "llm_truncated": 502,
    "llm_unavailable": 502,
}


def to_api_error(
    state: UpstreamState, retry_after_seconds: int | None = None
) -> ApiError:
    """The error of the state, with its Retry-After when it has one."""
    headers = (
        None
        if retry_after_seconds is None
        else {"Retry-After": str(retry_after_seconds)}
    )
    return ApiError(STATUS_BY_STATE[state], state, headers)


def describe_upstream_errors(
    states: Iterable[UpstreamState],
) -> dict[int | str, dict[str, Any]]:
    """The states of each upstream status, for the OpenAPI."""
    by_status = sorted(
        ((state, STATUS_BY_STATE[state]) for state in states),
        key=lambda pair: (pair[1], pair[0]),
    )
    return {
        status: {
            "model": ErrorSchema,
            "description": ", ".join(state for state, _ in pairs),
        }
        for status, pairs in groupby(by_status, key=lambda pair: pair[1])
    }


def describe_error_responses(
    states: Iterable[UpstreamState],
) -> dict[int | str, dict[str, Any]]:
    """The error bodies of a route whose upstream states are these, for the OpenAPI."""
    return {
        **API_ERROR_RESPONSES,
        500: {"model": ErrorSchema, "description": "internal_error"},
        **describe_upstream_errors(states),
    }


# POST /digests reads the data API and calls the model; POST /trend-reports reads the data API and
# GitHub.
ERROR_RESPONSES = describe_error_responses(
    (*get_args(DataApiState.__value__), *get_args(LlmFailure.__value__))
)
TREND_REPORT_ERROR_RESPONSES = describe_error_responses(
    (*get_args(DataApiState.__value__), *get_args(GithubState.__value__))
)
