"""The pages of the digests of the watch, without input nor output: the subject and the day read from
the address, the page of a digest, of a subject without digest, and of a source the base no longer
holds under its number (docs/site-web.md, "Comptes rendus")."""

from dataclasses import dataclass
from datetime import datetime

from k_b.items import WATCH_KINDS, WatchKind, make_visible
from k_b.web.data_api_client import (
    DigestDays,
    DigestSource,
    ItemDetail,
    WatchDigest,
)
from k_b.web.feed import (
    LABELS_BY_KIND,
    NEW_TAB_NOTE,
    NO_TITLE,
    keep_https_link,
)
from k_b.web.french_dates import write_count, write_day
from k_b.web.item_detail import BackLink, Day, to_day
from k_b.web.received_text import clean_received_value

DIGESTS_PATH = "/comptes-rendus"
SUBJECT_PATH = "/comptes-rendus/{subject}"
DAY_PATH = "/comptes-rendus/{subject}/{day}"
SOURCE_PATH = "/comptes-rendus/{subject}/{day}/sources/{item_id}"
# The words of the sheet of a digest without claim (post/digest_sheets.py, NO_CLAIM and NO_ITEM),
# held equal by a test: the site does not import post.
EMPTY_TEXT_BY_OUTCOME = {
    "no_claim": "Aucune affirmation retenue.",
    "no_item": "Aucun item classé dans ce sujet.",
}
# A claim the cleaning leaves without a letter: TEXT_CHARS lets through one of format characters.
NO_TEXT = "Sans texte."
NO_DIGEST_TEXT = "Aucun compte rendu pour ce sujet."
SOURCE_LINK_LABEL = "Lire la source"
# The kinds whose plural is feminine: the kinds read in full, all of them feminine, take "lues".
FEMININE_KINDS: frozenset[WatchKind] = frozenset(
    {"vulnerability", "advisory", "release"}
)


@dataclass(frozen=True)
class Subject:
    """A subject as the site names it, and the line that says what it holds."""

    label: str
    description: str


# The subjects of DIGEST_SUBJECTS (core/config.py), in its order; a test keeps both lists equal.
# Written for the site: the definitions of DIGEST_SUBJECTS are the ones
# the model reads.
SUBJECTS: dict[str, Subject] = {
    "vulnerabilities": Subject(
        "Vulnérabilités",
        "Les failles répertoriées, exploitées ou signalées sur les paquets suivis, et les"
        " articles qui les décrivent.",
    ),
    "llm_security": Subject(
        "Sécurité des LLM et des agents",
        "Les attaques et les défenses propres aux LLM et aux agents: injection"
        " d’instructions, contournement, empoisonnement, porte dérobée.",
    ),
    "agent_frameworks": Subject(
        "Frameworks agentiques",
        "Les versions et les nouvelles de LangChain, LangGraph, LlamaIndex et des autres"
        " frameworks agentiques.",
    ),
    "coding_assistants": Subject(
        "Assistants de code",
        "Les assistants de code: leurs versions, leurs fonctions, leurs usages.",
    ),
    "models": Subject(
        "Modèles",
        "Les nouveaux modèles, leurs évaluations, leurs capacités et les limites annoncées.",
    ),
    "ai_industry": Subject(
        "Industrie de l’IA",
        "Les entreprises, les produits, les financements et la régulation de l’IA.",
    ),
    "cybersecurity": Subject(
        "Cybersécurité",
        "Les incidents, les campagnes d’attaque, les outils et les pratiques de sécurité,"
        " hors IA et hors failles répertoriées.",
    ),
    "software_engineering": Subject(
        "Développement logiciel",
        "Les outils, les langages et les pratiques du développement, hors IA.",
    ),
    "tech_industry": Subject(
        "Industrie de la tech",
        "Les entreprises, les produits, les plateformes et le matériel de la tech, hors IA.",
    ),
}


@dataclass(frozen=True)
class SubjectLink:
    href: str
    label: str
    description: str


@dataclass(frozen=True)
class SourceLink:
    """A source under its claim: its title leads to the page that checks it (SOURCE_PATH)."""

    href: str
    title: str
    title_lang: str | None


@dataclass(frozen=True)
class ClaimView:
    text: str
    sources: tuple[SourceLink, ...]


@dataclass(frozen=True)
class KindName:
    """A kind in the words of the form of the feed, in lower case."""

    label: str
    lang: str | None


@dataclass(frozen=True)
class CutKind:
    """The kind cut by the reading, and the moment after which its items are read."""

    name: KindName
    after: Day


@dataclass(frozen=True)
class CapNotice:
    """What the cut of the reading left out of the window of the subject: the reading goes through
    WATCH_KINDS in order and stops at the cut (ai_api/connectors/data_api_client.py, list_items)."""

    # None: the first item left out is older than the window, whose items of the kind are all read.
    cut: CutKind | None
    unread: tuple[KindName, ...]
    whole: tuple[KindName, ...]
    # The participle of "ont été ... en entier", agreed with the kinds read in full.
    whole_participle: str


@dataclass(frozen=True)
class DayLink:
    """A day of the subject; the day shown is marked, without a link."""

    day: Day
    href: str
    is_current: bool


@dataclass(frozen=True)
class DigestPage:
    """A digest as its page shows it, every text received cleaned."""

    page_title: str
    heading: str
    window_start: Day
    window_end: Day
    model: str
    cap: CapNotice | None
    claims: tuple[ClaimView, ...]
    # None: the digest has its claims.
    empty_text: str | None
    days: tuple[DayLink, ...]
    # None: every day of the subject is listed.
    days_note: str | None


@dataclass(frozen=True)
class AbsentDigestPage:
    page_title: str
    heading: str
    text: str


@dataclass(frozen=True)
class MissingSourcePage:
    """A source of a digest that its number no longer leads to (is_item_of_source)."""

    page_title: str
    back_link: BackLink
    text: str
    title: str
    title_lang: str | None
    # None: a URL out of https, never made a link.
    link: str | None
    link_label: str
    link_note: str


def build_subject_links() -> tuple[SubjectLink, ...]:
    return tuple(
        SubjectLink(
            SUBJECT_PATH.format(subject=name), subject.label, subject.description
        )
        for name, subject in SUBJECTS.items()
    )


def build_digest_page(digest: WatchDigest, days: DigestDays) -> DigestPage:
    """A digest, its claims in the order of the sheet, each with its sources in the order it cites
    them, and the days of its subject, the most recent first."""
    label = SUBJECTS[digest.subject].label
    day = write_day(digest.day)
    sources = {source.item_id: source for source in digest.sources}
    return DigestPage(
        page_title=f"{label}, compte rendu du {day}",
        heading=f"{label}, {day}",
        window_start=to_day(digest.since),
        window_end=to_day(digest.until),
        model=digest.model,
        cap=build_cap_notice(digest),
        claims=tuple(
            ClaimView(
                clean_received_value(claim.text) or NO_TEXT,
                tuple(
                    build_source_link(digest, sources[item_id])
                    for item_id in claim.item_ids
                ),
            )
            for claim in digest.claims
        ),
        empty_text=EMPTY_TEXT_BY_OUTCOME.get(digest.outcome),
        days=tuple(
            DayLink(
                Day(listed.isoformat(), write_day(listed)),
                DAY_PATH.format(subject=digest.subject, day=listed.isoformat()),
                listed == digest.day,
            )
            for listed in days.days
        ),
        days_note=write_days_note(days),
    )


def build_cap_notice(digest: WatchDigest) -> CapNotice | None:
    """The kinds read in full, cut and not read; None when the window of the subject misses none.
    since is the subject's own, covered_after the one of the reading of every subject."""
    if digest.capped_kind is None or digest.covered_after is None:
        return None
    position = WATCH_KINDS.index(digest.capped_kind)
    # covered_after is the first item left out, bound excluded: in the window, items are missing.
    is_cut_in_window = digest.covered_after >= digest.since
    whole = WATCH_KINDS[: position if is_cut_in_window else position + 1]
    unread = WATCH_KINDS[position + 1 :]
    if not is_cut_in_window and not unread:
        return None
    cut = CutKind(name_kind(digest.capped_kind), to_moment(digest.covered_after))
    return CapNotice(
        cut=cut if is_cut_in_window else None,
        unread=tuple(map(name_kind, unread)),
        whole=tuple(map(name_kind, whole)),
        whole_participle="lues" if FEMININE_KINDS.issuperset(whole) else "lus",
    )


def name_kind(kind: WatchKind) -> KindName:
    labels = LABELS_BY_KIND[kind]
    return KindName(labels.form_label.lower(), labels.label_lang)


def to_moment(moment: datetime) -> Day:
    """A moment as its time element gives it, to the second, the bound of a cut being exclusive: ISO
    in UTC for the machine, the month in letters for people."""
    return Day(
        moment.isoformat(timespec="seconds").replace("+00:00", "Z"),
        f"{write_day(moment)} à {moment:%H:%M:%S} UTC",
    )


def build_source_link(digest: WatchDigest, source: DigestSource) -> SourceLink:
    """In English by hypothesis, as the titles of the feed."""
    title = clean_received_value(source.title)
    return SourceLink(
        href=SOURCE_PATH.format(
            subject=digest.subject, day=digest.day.isoformat(), item_id=source.item_id
        ),
        title=title or NO_TITLE,
        title_lang="en" if title else None,
    )


def write_days_note(days: DigestDays) -> str | None:
    """Beyond the days listed, how many the subject has: the site asks no other page of them."""
    if days.total <= len(days.days):
        return None
    return (
        f"Les {write_count(len(days.days))} jours les plus récents sur"
        f" {write_count(days.total)}."
    )


def build_absent_digest_page(subject: str) -> AbsentDigestPage:
    label = SUBJECTS[subject].label
    return AbsentDigestPage(f"{label}, aucun compte rendu", label, NO_DIGEST_TEXT)


def build_digest_back_link(digest: WatchDigest) -> BackLink:
    return BackLink(
        DAY_PATH.format(subject=digest.subject, day=digest.day.isoformat()),
        "Retour au compte rendu",
    )


def write_source_title(digest: WatchDigest, item_title: str) -> str:
    """The title of the page of an item reached from a digest: its own, as RGAA 8.6 asks, which
    names the digest it is a source of."""
    return (
        f"{item_title}, source du compte rendu {SUBJECTS[digest.subject].label}"
        f" du {write_day(digest.day)}"
    )


def find_source(digest: WatchDigest, item_id: int) -> DigestSource | None:
    return next(
        (source for source in digest.sources if source.item_id == item_id), None
    )


def is_item_of_source(detail: ItemDetail, source: DigestSource) -> bool:
    """Whether the item is the source: its URL when the source has one, which a paper retitled in
    place keeps (database/writers/paper_writer.py) and vulnerabilities of the CISA KEV, sharing
    their title, never share; else its title on one line, as the twin writes it (make_visible). A
    base made again numbers its items anew (docs/specs-api.md, GET /digests/{subject}, limit (d))."""
    if source.url is not None:
        return source.url == detail.url
    return make_visible(detail.title) == source.title


def build_missing_source_page(
    digest: WatchDigest, source: DigestSource
) -> MissingSourcePage:
    """What is observed, the title of the source and the link to its page if it is https."""
    title = clean_received_value(source.title)
    return MissingSourcePage(
        page_title=f"Source introuvable, n° {source.item_id} du compte rendu"
        f" {SUBJECTS[digest.subject].label} du {write_day(digest.day)}",
        back_link=build_digest_back_link(digest),
        text=f"Le n° {source.item_id} de la base de K-B ne mène pas à cette source.",
        title=title or NO_TITLE,
        title_lang="en" if title else None,
        link=keep_https_link(source.url),
        link_label=SOURCE_LINK_LABEL,
        # The site knows neither the kind of a source nor the language of its page: the note alone,
        # as on the card of a newsletter article.
        link_note=NEW_TAB_NOTE,
    )
