"""The pages of the digests, /comptes-rendus, served by the site on its simulated data API: the
subjects, the digest of a subject, its states, its errors, the link of each source to its item,
and the budget of the screen (docs/site-web.md, "Comptes rendus")."""

import logging
import re

import httpx2
import pytest
from digest_fixture import (
    DAY,
    DAY_PATH,
    DIGEST,
    DIGEST_PATH,
    NOT_FOUND,
    SUBJECT,
    make_digest,
    serve_digests,
)
from item_fixture import ITEM_DETAILS, VULNERABILITY, make_detail
from screen_weight import SCREEN_BUDGET_BYTES, SCREEN_RESOURCES, weigh_screen
from site_client import OPERATOR_HEADERS, make_client

from k_b.core.config import (
    DIGEST_SUBJECTS,
    ITEMS_PER_CLAIM,
    MAX_CLAIMS,
    MAX_ITEMS_PER_DIGEST,
    TEXT_CHARS,
)
from k_b.post.digest_sheets import NO_CLAIM, NO_ITEM
from k_b.web.digests import EMPTY_TEXT_BY_OUTCOME, SUBJECTS

INDEX_PATH = "/comptes-rendus"
SOURCE_PATH = f"{DAY_PATH}/sources"
SOURCE_LINK = re.compile(r'<a href="(/comptes-rendus/[^"]+/sources/[0-9]+)" lang="en">')


def make_excluded_item(kind):
    """A Zotero entry or a clip under the id of a source, as test_item_page.py serves one."""
    return {
        "id": 9,
        "kind": kind,
        "title": "A private page kept",
        "source_date": "2026-10-07T00:00:00Z",
        "url": None,
        "withdrawn_at": None,
        "body": "secret-clip-text",
    }


def get(path, handler):
    return make_client(handler=handler).get(path, headers=OPERATOR_HEADERS)


def read_claims(response):
    """Each claim of the page, in order: its text, and what follows it up to the next claim."""
    claims = re.search(r'<ol class="claims">(.*?)</ol>', response.text, flags=re.DOTALL)
    assert claims is not None
    parts = claims.group(1).split('<li class="claim">')[1:]
    return [
        (re.search(r'<p class="claim-text">([^<]*)</p>', part).group(1), part)
        for part in parts
    ]


# --- The subjects.


def test_the_subjects_are_those_of_the_digests_in_their_order():
    """Sabine names the subjects (2026-11-26): a subject added to DIGEST_SUBJECTS gets its label."""
    assert tuple(SUBJECTS) == tuple(subject.name for subject in DIGEST_SUBJECTS)


def test_the_labels_are_those_sabine_gave():
    """2026-11-26: Vulnérabilités, Frameworks agentiques; LLM stays LLM."""
    assert SUBJECTS["vulnerabilities"].label == "Vulnérabilités"
    assert SUBJECTS["llm_security"].label == "Sécurité des LLM et des agents"
    assert SUBJECTS["agent_frameworks"].label == "Frameworks agentiques"


def test_the_index_lists_each_subject_with_its_link_without_asking_the_data_api():
    handler, requests = serve_digests()

    response = get(INDEX_PATH, handler)

    assert response.status_code == 200
    assert requests == []
    assert "<title>Comptes rendus de veille · K-B</title>" in response.text
    assert re.findall(
        r'<h2 class="card-title"><a href="([^"]+)">([^<]+)</a></h2>', response.text
    ) == [
        (f"/comptes-rendus/{name}", subject.label) for name, subject in SUBJECTS.items()
    ]


# --- A digest.


def test_the_latest_digest_of_a_subject_asks_it_without_a_day_then_its_days():
    handler, requests = serve_digests()

    response = get(DIGEST_PATH, handler)

    assert response.status_code == 200
    assert [request.url.path for request in requests] == [
        f"/digests/{SUBJECT}",
        f"/digests/{SUBJECT}/days",
    ]
    assert "day" not in requests[0].url.params
    assert (
        "<title>Frameworks agentiques, compte rendu du 23 novembre 2026 · K-B</title>"
        in response.text
    )
    assert "<h1>Frameworks agentiques, 23 novembre 2026</h1>" in response.text


def test_a_day_asked_sends_its_day():
    handler, requests = serve_digests()

    response = get(DAY_PATH, handler)

    assert response.status_code == 200
    assert requests[0].url.params["day"] == DAY


def test_the_window_is_given_by_its_first_and_last_day():
    response = get(DIGEST_PATH, serve_digests()[0])

    assert (
        'Fenêtre du <time datetime="2026-11-19">19 novembre 2026</time> au'
        ' <time datetime="2026-11-23">23 novembre 2026</time>' in response.text
    )


def test_the_model_named_is_the_one_of_the_answer():
    """Never written in the site: the model of each digest, read in its twin."""
    response = get(DIGEST_PATH, serve_digests(make_digest(model="gpt-6-luna"))[0])

    assert (
        'Rédigé par le LLM (grand modèle de langage) <span class="item-code">gpt-6-luna</span>'
        in response.text
    )
    assert "gpt-6.1-sol" not in response.text


def test_each_claim_is_followed_by_the_links_of_its_sources_in_its_order():
    response = get(DIGEST_PATH, serve_digests()[0])

    claims = read_claims(response)
    assert [text for text, _ in claims] == [claim["text"] for claim in DIGEST["claims"]]
    assert [SOURCE_LINK.findall(sources) for _, sources in claims] == [
        [f"{SOURCE_PATH}/9"],
        [f"{SOURCE_PATH}/10", f"{SOURCE_PATH}/17"],
    ]
    first_sources = claims[0][1]
    assert "Source:" in first_sources
    assert "Sources:" in claims[1][1]
    assert f'lang="en">{ITEM_DETAILS[9]["title"]}</a>' in first_sources


def test_the_links_of_the_latest_digest_lead_to_its_own_day():
    """The address of a source names the day of the digest it belongs to, never latest."""
    response = get(DIGEST_PATH, serve_digests()[0])

    assert all(
        link.startswith(f"{DAY_PATH}/") for link in SOURCE_LINK.findall(response.text)
    )


def test_the_days_lead_to_their_digest_the_day_shown_marked_without_a_link():
    response = get(DAY_PATH, serve_digests()[0])

    days = re.search(
        r'<ul class="days" role="list">(.*?)</ul>', response.text, re.DOTALL
    )
    assert days is not None
    assert re.findall(r'<a href="([^"]+)">', days.group(1)) == [
        f"{DIGEST_PATH}/2026-11-19",
        f"{DIGEST_PATH}/2026-11-16",
        f"{DIGEST_PATH}/2026-11-12",
    ]
    assert (
        '<span aria-current="page"><time datetime="2026-11-23">23 novembre 2026</time></span>'
        in days.group(1)
    )


def test_beyond_thirty_days_the_list_says_how_many_it_shows():
    days = {"days": [f"2026-10-{day:02d}" for day in range(30, 0, -1)], "total": 45}

    response = get(DIGEST_PATH, serve_digests(days=days)[0])

    assert response.text.count('<time datetime="2026-10-') == 30
    assert (
        '<p class="table-note">Les 30 jours les plus récents sur 45.</p>'
        in response.text
    )


def test_thirty_days_or_fewer_are_all_shown_without_a_note():
    response = get(DIGEST_PATH, serve_digests()[0])

    assert "jours les plus récents" not in response.text


# --- The states of a digest.


def test_the_words_of_a_digest_without_claim_are_those_of_its_sheet():
    """The site cannot import post: the words of post/digest_sheets.py are held equal here."""
    assert EMPTY_TEXT_BY_OUTCOME == {"no_claim": NO_CLAIM, "no_item": NO_ITEM}


@pytest.mark.parametrize(
    ("outcome", "text"),
    [
        ("no_claim", "Aucune affirmation retenue."),
        ("no_item", "Aucun item classé dans ce sujet."),
    ],
)
def test_a_digest_without_claim_says_why_in_the_words_of_its_sheet(outcome, text):
    digest = make_digest(outcome=outcome, claims=[], sources=[])

    response = get(DIGEST_PATH, serve_digests(digest)[0])

    assert response.status_code == 200
    assert f'<p class="results-line">{text}</p>' in response.text
    assert '<ol class="claims">' not in response.text
    assert "Rédigé par" not in response.text
    assert '<ul class="days" role="list">' in response.text


CUT_RELEASES = (
    'Parmi les <span lang="en">releases</span>, K-B n’a lu que les items publiés après le'
    ' <time datetime="2026-11-21T09:05:40Z">21 novembre 2026 à 09:05:40 UTC</time> (temps'
    " universel coordonné): les plus anciens de la fenêtre n’y sont pas."
)


@pytest.mark.parametrize(
    ("capped_kind", "covered_after", "text"),
    [
        # The reading goes through the kinds in the order of WATCH_KINDS and stops at the cut: the
        # kinds after it are not read at all (ai_api/connectors/data_api_client.py, list_items).
        (
            "release",
            "2026-11-21T09:05:40Z",
            (
                f"{CUT_RELEASES} Les articles de newsletters n’ont pas été lus. Les failles, les"
                " alertes et les papiers ont été lus en entier."
            ),
        ),
        # The first item left out is older than the window of the subject (its since): every
        # paper of the window is read, the kinds after are not.
        (
            "paper",
            "2026-11-18T00:00:00Z",
            (
                'Les <span lang="en">releases</span> et les articles de newsletters n’ont pas été'
                " lus. Les failles, les alertes et les papiers ont été lus en entier."
            ),
        ),
        # Feminine kinds only: the participle agrees.
        (
            "advisory",
            "2026-11-21T09:05:40Z",
            (
                "Parmi les alertes, K-B n’a lu que les items publiés après le <time"
                ' datetime="2026-11-21T09:05:40Z">21 novembre 2026 à 09:05:40 UTC</time> (temps'
                " universel coordonné): les plus anciens de la fenêtre n’y sont pas. Les papiers,"
                ' les <span lang="en">releases</span> et les articles de newsletters n’ont pas été'
                " lus. Les failles ont été lues en entier."
            ),
        ),
        # Cut on the first kind: none is read whole.
        (
            "vulnerability",
            "2026-11-21T09:05:40Z",
            (
                "Parmi les failles, K-B n’a lu que les items publiés après le <time"
                ' datetime="2026-11-21T09:05:40Z">21 novembre 2026 à 09:05:40 UTC</time> (temps'
                " universel coordonné): les plus anciens de la fenêtre n’y sont pas. Les alertes,"
                ' les papiers, les <span lang="en">releases</span> et les articles de newsletters'
                " n’ont pas été lus."
            ),
        ),
        # Cut on the last kind: every other is read whole.
        (
            "newsletter_article",
            "2026-11-21T00:00:00Z",
            (
                "Parmi les articles de newsletters, K-B n’a lu que les items publiés après le <time"
                ' datetime="2026-11-21T00:00:00Z">21 novembre 2026 à 00:00:00 UTC</time> (temps'
                " universel coordonné): les plus anciens de la fenêtre n’y sont pas. Les failles,"
                ' les alertes, les papiers et les <span lang="en">releases</span> ont été lus en'
                " entier."
            ),
        ),
    ],
    ids=["release", "paper-before-since", "advisory", "vulnerability", "newsletter"],
)
def test_a_digest_cut_says_in_words_what_was_read_and_what_was_not(
    capped_kind, covered_after, text
):
    """OWASP LLM07: a digest cut must not look whole; RGAA 3.1: said in words. The moment is given
    to the second: its bound is exclusive."""
    digest = make_digest(
        items_capped=True, capped_kind=capped_kind, covered_after=covered_after
    )

    response = get(DIGEST_PATH, serve_digests(digest)[0])

    assert '<p class="banner-title">Compte rendu partiel</p>' in response.text
    assert f'<p class="banner-text">{text}</p>' in response.text


def test_a_cut_that_leaves_nothing_out_of_the_subject_has_no_banner():
    """Cut on the last kind, its first item left out older than the window of the subject."""
    digest = make_digest(
        items_capped=True,
        capped_kind="newsletter_article",
        covered_after="2026-11-18T00:00:00Z",
    )

    response = get(DIGEST_PATH, serve_digests(digest)[0])

    assert response.status_code == 200
    assert "banner" not in response.text


def test_the_moment_of_a_cut_is_written_to_the_second_in_its_time_element():
    """HTML allows 1 to 3 digits of fraction only."""
    digest = make_digest(
        items_capped=True,
        capped_kind="release",
        covered_after="2026-11-21T09:05:40.123456Z",
    )

    response = get(DIGEST_PATH, serve_digests(digest)[0])

    assert CUT_RELEASES in response.text


def test_a_digest_whole_has_no_banner():
    response = get(DIGEST_PATH, serve_digests()[0])

    assert "banner" not in response.text


def test_a_subject_without_digest_is_said_in_200_without_asking_its_days():
    handler, requests = serve_digests(NOT_FOUND, digest_status=404)

    response = get(DIGEST_PATH, handler)

    assert response.status_code == 200
    assert len(requests) == 1
    assert (
        "<title>Frameworks agentiques, aucun compte rendu · K-B</title>"
        in response.text
    )
    assert (
        '<p class="results-line">Aucun compte rendu pour ce sujet.</p>' in response.text
    )
    assert '<a class="back-link" href="/comptes-rendus">' in response.text


def test_a_day_without_digest_is_the_page_not_found():
    response = get(DAY_PATH, serve_digests(NOT_FOUND, digest_status=404)[0])

    assert response.status_code == 404


@pytest.mark.parametrize(
    "path",
    [
        "/comptes-rendus/no_such_subject",
        "/comptes-rendus/Agent_frameworks",
        f"/comptes-rendus/no_such_subject/{DAY}",
        f"{DIGEST_PATH}/2026-02-30",
        f"{DIGEST_PATH}/2026-11-3",
        f"{DIGEST_PATH}/23-11-2026",
        f"{DAY_PATH}/sources/09",
        f"{DAY_PATH}/sources/abc",
        f"{DIGEST_PATH}/2026-02-30/sources/9",
        "/comptes-rendus/",
    ],
)
def test_an_address_out_of_its_form_is_the_page_not_found_without_asking_the_data_api(
    path,
):
    handler, requests = serve_digests()

    response = get(path, handler)

    assert response.status_code == 404
    assert requests == []


# --- The errors.


def test_a_failure_of_the_data_api_gives_the_page_500_logged_without_the_subject(
    caplog,
):
    with caplog.at_level(logging.INFO, logger="k_b"):
        response = get(
            DAY_PATH,
            serve_digests({"error": "watch_unconfigured"}, digest_status=503)[0],
        )

    assert response.status_code == 500
    [line] = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("data_api_failed")
    ]
    assert line.startswith(
        "data_api_failed: data_api_unavailable http_status=503 request_id="
    )
    assert DAY not in caplog.text
    assert SUBJECT not in caplog.text
    assert "route=/comptes-rendus/{subject}/{day}" in caplog.text


def test_days_out_of_the_contract_give_the_page_500():
    response = get(DIGEST_PATH, serve_digests(days={"days": [], "total": -1})[0])

    assert response.status_code == 500


def test_a_digest_of_another_subject_gives_the_page_500():
    response = get(DIGEST_PATH, serve_digests(make_digest(subject="models"))[0])

    assert response.status_code == 500


# --- A text received, shown as text.


def test_a_text_of_the_model_or_of_a_source_is_shown_as_text_never_as_a_link():
    """OWASP LLM10: a tag, an address and a bidirectional control in the output of the model."""
    trap = f"<a href=x>Lire</a> https://example.org/x {chr(0x202E)}fin"
    digest = make_digest(
        claims=[{"text": trap, "item_ids": [9]}],
        sources=[{"item_id": 9, "title": trap, "url": "https://example.org/x"}],
    )

    response = get(DIGEST_PATH, serve_digests(digest)[0])

    assert response.status_code == 200
    assert "&lt;a href=x&gt;Lire&lt;/a&gt; https://example.org/x fin" in response.text
    assert chr(0x202E) not in response.text
    assert 'href="https://example.org' not in response.text
    assert "<a href=x>" not in response.text


def test_a_text_the_cleaning_leaves_empty_is_named():
    digest = make_digest(
        claims=[{"text": chr(0x200B), "item_ids": [9]}],
        sources=[{"item_id": 9, "title": chr(0x200B), "url": None}],
    )

    response = get(DIGEST_PATH, serve_digests(digest)[0])

    assert '<p class="claim-text">Sans texte.</p>' in response.text
    assert f'<a href="{SOURCE_PATH}/9">Sans titre</a>' in response.text


# --- The link of a source.


def test_a_source_whose_item_has_its_title_leads_to_the_page_of_the_item():
    handler, requests = serve_digests()

    response = get(f"{SOURCE_PATH}/9", handler)

    assert response.status_code == 200
    assert [request.url.path for request in requests] == [
        f"/digests/{SUBJECT}",
        "/items/9",
    ]
    assert requests[0].url.params["day"] == DAY
    assert f'<h1 lang="en">{ITEM_DETAILS[9]["title"]}</h1>' in response.text
    assert (
        "<title>Alerte GHSA-fjqc-hq36-qh5p, source du compte rendu Frameworks agentiques"
        " du 23 novembre 2026 · K-B</title>" in response.text
    )
    assert (
        f'<a class="back-link" href="{DAY_PATH}"><span aria-hidden="true">←</span>'
        " Retour au compte rendu</a>" in response.text
    )


def test_the_title_is_compared_on_one_line_as_the_twin_writes_it():
    """make_visible, the rule of the writer of the twin (post/digest_sheets.py)."""
    detail = make_detail(9, title="LangGraph\tCheckpoint:\n Unsafe JSON")
    digest = make_digest(
        claims=[{"text": "Une affirmation.", "item_ids": [9]}],
        sources=[
            {"item_id": 9, "title": "LangGraph Checkpoint: Unsafe JSON", "url": None}
        ],
    )

    response = get(f"{SOURCE_PATH}/9", serve_digests(digest, items={9: detail})[0])

    assert "Retour au compte rendu" in response.text
    assert "Source introuvable" not in response.text


def test_the_detail_of_the_feed_keeps_its_way_back_to_the_feed():
    response = get("/items/9", serve_digests()[0])

    assert (
        '<a class="back-link" href="/"><span aria-hidden="true">←</span> Retour au fil</a>'
        in response.text
    )


@pytest.mark.parametrize(
    "items",
    [
        # Another item under the same id: a base made again numbers its items anew.
        {9: make_detail(9, title="Another title")},
        # No item of this id in the base.
        {},
        # A Zotero entry or a clip, never shown.
        {9: make_excluded_item("zotero_entry")},
        {9: make_excluded_item("clip")},
    ],
    ids=["other-title", "absent", "zotero-entry", "clip"],
)
def test_a_source_without_its_item_is_said_with_its_title_and_its_link(items):
    response = get(f"{SOURCE_PATH}/9", serve_digests(items=items)[0])

    assert response.status_code == 200
    assert "<h1>Source introuvable</h1>" in response.text
    assert "Le n° 9 de la base de K-B ne mène pas à cette source." in response.text
    assert f'<dd lang="en">{ITEM_DETAILS[9]["title"]}</dd>' in response.text
    assert f'href="{ITEM_DETAILS[9]["url"]}" hreflang="en"' in response.text
    assert "(en anglais, site externe, nouvel onglet)" in response.text
    assert "Another title" not in response.text
    assert "A private page kept" not in response.text
    assert "secret-clip-text" not in response.text
    assert (
        f'<a class="back-link" href="{DAY_PATH}"><span aria-hidden="true">←</span>'
        " Retour au compte rendu</a>" in response.text
    )


def test_a_source_whose_item_has_its_title_under_another_url_is_not_found():
    """Vulnerabilities of the CISA KEV catalog share their vulnerabilityName: a base made again can
    give the id of a source to another CVE of the same title, never of the same URL."""
    vulnerability = ITEM_DETAILS[VULNERABILITY]
    digest = make_digest(
        claims=[{"text": "Une affirmation.", "item_ids": [VULNERABILITY]}],
        sources=[
            {
                "item_id": VULNERABILITY,
                "title": vulnerability["title"],
                "url": vulnerability["url"],
            }
        ],
    )
    other_cve = make_detail(
        VULNERABILITY, url="https://nvd.nist.gov/vuln/detail/CVE-2026-86951"
    )

    response = get(
        f"{SOURCE_PATH}/{VULNERABILITY}",
        serve_digests(digest, items={VULNERABILITY: other_cve})[0],
    )

    assert response.status_code == 200
    assert "<h1>Source introuvable</h1>" in response.text
    assert "CVE-2026-86951" not in response.text


def test_a_source_without_an_https_url_has_no_link_to_its_page():
    digest = make_digest(
        claims=[{"text": "Une affirmation.", "item_ids": [9]}],
        sources=[{"item_id": 9, "title": "Un titre", "url": "http://example.org/x"}],
    )

    response = get(f"{SOURCE_PATH}/9", serve_digests(digest, items={})[0])

    assert "Source introuvable" in response.text
    assert "example.org" not in response.text


def test_a_source_absent_from_the_digest_is_the_page_not_found_without_reading_an_item():
    handler, requests = serve_digests()

    response = get(f"{SOURCE_PATH}/6", handler)

    assert response.status_code == 404
    assert [request.url.path for request in requests] == [f"/digests/{SUBJECT}"]


def test_a_source_of_a_day_without_digest_is_the_page_not_found():
    response = get(f"{SOURCE_PATH}/9", serve_digests(NOT_FOUND, digest_status=404)[0])

    assert response.status_code == 404


def test_a_failure_reading_the_item_of_a_source_gives_the_page_500():
    serve_digest, _ = serve_digests()

    def handler(request):
        if request.url.path.startswith("/items/"):
            return httpx2.Response(503, json={"error": "query_timeout"})
        return serve_digest(request)

    response = get(f"{SOURCE_PATH}/9", handler)

    assert response.status_code == 500


# --- The budget of the screen.


def test_the_screen_of_a_digest_holds_three_requests_and_30_kb_at_most():
    """RGESN 6.1 (D4 of #564): 12 claims of 400 characters, 60 sources of 140 characters, 30
    days."""
    sources = [
        {
            "item_id": 1000 + index,
            "title": f"{index:03d} " + "t" * 136,
            "url": f"https://example.org/{index}",
        }
        for index in range(MAX_ITEMS_PER_DIGEST)
    ]
    per_claim = ITEMS_PER_CLAIM[1]
    claims = [
        {
            "text": f"{index:03d} " + "a" * (TEXT_CHARS[1] - 4),
            "item_ids": [
                source["item_id"]
                for source in sources[index * per_claim : (index + 1) * per_claim]
            ],
        }
        for index in range(MAX_CLAIMS)
    ]
    days = {
        "days": [
            f"2026-{month:02d}-{day:02d}"
            for month in (11, 10)
            for day in range(28, 13, -1)
        ],
        "total": 60,
    }
    client = make_client(
        handler=serve_digests(make_digest(claims=claims, sources=sources), days)[0]
    )

    screen = weigh_screen(client, DIGEST_PATH)

    assert screen.status_code == 200
    assert screen.resources == SCREEN_RESOURCES
    assert screen.weight <= SCREEN_BUDGET_BYTES
