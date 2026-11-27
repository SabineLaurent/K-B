"""A digest for the site: the answer of GET /digests/{subject} of the data API, its sources the
advisories of the test base (tests/fixtures/items_database.sql) under their titles, its claims written
for the tests; the answer of GET /digests/{subject}/days; and a data API that serves both and the
detail of an item."""

import copy

import httpx2
from item_fixture import ADVISORY_ABSENT_FROM_CATALOG, ADVISORY_IN_CATALOG, ITEM_DETAILS
from item_fixture import ADVISORY_WITHOUT_CVE as ADVISORY_OF_LANGCHAIN

SUBJECT = "agent_frameworks"
DAY = "2026-11-23"
DIGEST_PATH = f"/comptes-rendus/{SUBJECT}"
DAY_PATH = f"{DIGEST_PATH}/{DAY}"
NOT_FOUND = {"error": "digest_not_found"}
SOURCE_IDS = (ADVISORY_IN_CATALOG, ADVISORY_OF_LANGCHAIN, ADVISORY_ABSENT_FROM_CATALOG)


def make_source(item_id):
    """A source as the twin of its sheet holds it: its title, the title of its item."""
    detail = ITEM_DETAILS[item_id]
    return {"item_id": item_id, "title": detail["title"], "url": detail["url"]}


DIGEST = {
    "subject": SUBJECT,
    "day": DAY,
    "since": "2026-11-19T10:00:00Z",
    "until": "2026-11-23T10:00:00Z",
    "model": "gpt-6.1-sol",
    "items_capped": False,
    "capped_kind": None,
    "covered_after": None,
    "outcome": "written",
    "claims": [
        {
            "text": "LangGraph corrige une désérialisation JSON non sûre au chargement de"
            " ses points de reprise.",
            "item_ids": [ADVISORY_IN_CATALOG],
        },
        {
            "text": "LangChain corrige une traversée de chemin dans son intergiciel de"
            " recherche de fichiers, et le kit de LangSmith ne charge plus un manifeste"
            " public sans contrôle.",
            "item_ids": [ADVISORY_OF_LANGCHAIN, ADVISORY_ABSENT_FROM_CATALOG],
        },
    ],
    "sources": [make_source(item_id) for item_id in SOURCE_IDS],
}
DAYS = {"days": [DAY, "2026-11-19", "2026-11-16", "2026-11-12"], "total": 4}


def make_digest(**changes):
    """A copy of the digest of the fixture, its fields changed by changes."""
    return {**copy.deepcopy(DIGEST), **changes}


def serve_digests(digest=DIGEST, days=DAYS, items=None, digest_status=200):
    """A data API that answers the digest of a subject, its days and the detail of the items given
    by id (those of the fixture by default, item_not_found for any other), and keeps each request
    it receives."""
    requests = []
    details = ITEM_DETAILS if items is None else items

    def handler(request):
        requests.append(request)
        path = request.url.path
        if path.endswith("/days"):
            return httpx2.Response(200, json=days)
        if path.startswith("/digests/"):
            return httpx2.Response(digest_status, json=digest)
        item_id = int(path.removeprefix("/items/"))
        if item_id in details:
            return httpx2.Response(200, json=details[item_id])
        return httpx2.Response(404, json={"error": "item_not_found"})

    return handler, requests
