"""Read the security advisories of a raw GitHub API response."""

import json
import re
from dataclasses import dataclass
from datetime import datetime

from k_b.cisa_kev import CVE_ID
from k_b.github_dates import parse_github_date

GHSA_ID = re.compile(r"GHSA(-[23456789cfghjmpqrvwx]{4}){3}")
ADVISORY_URL_PREFIX = "https://github.com/advisories/"
SEVERITIES = ("low", "medium", "high", "critical", "unknown")


@dataclass(frozen=True)
class Advisory:
    """An advisory, without the people it credits: not needed for the watch (GDPR minimisation)."""

    ghsa_id: str
    cve_id: str | None
    summary: str
    severity: str
    url: str
    published_at: datetime
    # GitHub may review an advisory days after publishing it: collections follow this date.
    reviewed_at: datetime
    packages: tuple[str, ...]


def read_advisories(raw_response: bytes) -> list[Advisory]:
    """One advisory per entry of a `GET /advisories` response, newest first."""
    entries = json.loads(raw_response)
    if not isinstance(entries, list):
        raise ValueError("expected a list of advisories")
    return [parse_advisory(entry, position) for position, entry in enumerate(entries)]


def parse_advisory(entry: object, position: int) -> Advisory:
    if not isinstance(entry, dict):
        raise ValueError(f"advisory {position}: not an object")
    ghsa_id = entry.get("ghsa_id")
    if not isinstance(ghsa_id, str) or not GHSA_ID.fullmatch(ghsa_id):
        raise ValueError(f"advisory {position}: not a GHSA identifier: {ghsa_id!r}")
    cve_id = entry.get("cve_id")
    if cve_id is not None and not (
        isinstance(cve_id, str) and CVE_ID.fullmatch(cve_id)
    ):
        raise ValueError(f"advisory {position}: not a CVE identifier: {cve_id!r}")
    summary = entry.get("summary")
    if not isinstance(summary, str):
        raise ValueError(f"advisory {position}: summary is not a string")
    severity = entry.get("severity")
    if severity not in SEVERITIES:
        raise ValueError(f"advisory {position}: unknown severity: {severity!r}")
    url = entry.get("html_url")
    if not isinstance(url, str) or not url.startswith(ADVISORY_URL_PREFIX):
        raise ValueError(
            f"advisory {position}: html_url is not a {ADVISORY_URL_PREFIX} URL"
        )
    return Advisory(
        ghsa_id=ghsa_id,
        cve_id=cve_id,
        summary=summary,
        severity=severity,
        url=url,
        published_at=parse_github_date(
            entry.get("published_at"), f"advisory {position}: published_at"
        ),
        reviewed_at=parse_github_date(
            entry.get("github_reviewed_at"), f"advisory {position}: github_reviewed_at"
        ),
        packages=parse_package_names(entry.get("vulnerabilities"), position),
    )


def parse_package_names(vulnerabilities: object, position: int) -> tuple[str, ...]:
    """The affected packages, each once: an advisory lists one package per vulnerable range."""
    if not isinstance(vulnerabilities, list):
        raise ValueError(f"advisory {position}: vulnerabilities is not a list")
    package_names: list[str] = []
    for vulnerability in vulnerabilities:
        package = (
            vulnerability.get("package") if isinstance(vulnerability, dict) else None
        )
        name = package.get("name") if isinstance(package, dict) else None
        if not isinstance(name, str):
            raise ValueError(
                f"advisory {position}: a vulnerability has no package name"
            )
        if name not in package_names:
            package_names.append(name)
    return tuple(package_names)
