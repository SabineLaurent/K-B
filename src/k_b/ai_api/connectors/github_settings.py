"""The GitHub token of the trend reports, read from KB_AI_GITHUB_TOKEN, without default (a secret:
fail closed), and never anonymous (docs/tendances.md, "GitHub")."""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import SecretStr

GITHUB_TOKEN_VARIABLE = "KB_AI_GITHUB_TOKEN"  # noqa: S105 — the variable's name, not a token
# A fine-grained token: a classic one carries scopes, more than reading public repositories needs
# (least privilege, docs/jeton-github.md).
FINE_GRAINED_PREFIX = "github_pat_"
TOKEN_CHARACTERS = re.compile(r"[A-Za-z0-9_]+")


@dataclass(frozen=True)
class GithubSettings:
    token: SecretStr


def read_github_settings_or_refusal(environ: Mapping[str, str]) -> GithubSettings | str:
    """The token, or why it is refused: never the token."""
    token = environ.get(GITHUB_TOKEN_VARIABLE)
    if not token:
        return f"{GITHUB_TOKEN_VARIABLE}: not set"
    if not TOKEN_CHARACTERS.fullmatch(token):
        return (
            f"{GITHUB_TOKEN_VARIABLE}: token with a character outside"
            f" {TOKEN_CHARACTERS.pattern}"
        )
    if not token.startswith(FINE_GRAINED_PREFIX):
        return f"{GITHUB_TOKEN_VARIABLE}: not a fine-grained token (prefix {FINE_GRAINED_PREFIX})"
    return GithubSettings(token=SecretStr(token))
