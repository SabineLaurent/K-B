"""The checks of a writing: the claims within their bounds and faithful are kept, and make the
digest of the subject."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from k_b.ai_api.stages.fidelity import check_claim
from k_b.ai_api.stages.writing import Claim, WritingOutput, is_within_claim_bounds
from k_b.ai_api.watch_items import WatchItem, WatchKind, to_item_ref

# A source URL is returned only with one of these schemes (docs/fiches-veille.md, "Réponse").
SOURCE_URL_SCHEMES = ("http://", "https://")


@dataclass(frozen=True)
class DigestClaim:
    text: str
    item_ids: tuple[int, ...]


@dataclass(frozen=True)
class DigestSource:
    """Read from the data API, never from the output of the model."""

    item_id: int
    kind: WatchKind
    title: str
    url: str | None


@dataclass(frozen=True)
class Digest:
    subject: str
    claims: tuple[DigestClaim, ...]
    sources: tuple[DigestSource, ...]
    # Sent for this subject and cited by no claim of the model.
    items_not_retained_in_output: tuple[int, ...]
    # Every fact of every claim of the output, a claim removed included.
    facts_checked: int
    facts_found: int
    claims_removed: int
    # Cited by the model, no longer cited once its claims are removed.
    items_removed_by_checks: tuple[int, ...]


def to_digest(
    subject: str, items_sent: Sequence[WatchItem], output: WritingOutput
) -> Digest:
    """The digest of a writing checked: the claims within their bounds and faithful, and what the
    code computes from them."""
    item_by_ref = {to_item_ref(item.item_id): item for item in items_sent}
    fidelities = [check_claim(claim, item_by_ref) for claim in output.claims]
    kept = [
        claim
        for claim, fidelity in zip(output.claims, fidelities, strict=True)
        if is_within_claim_bounds(claim) and fidelity.is_faithful
    ]
    cited_by_model = cited_refs(output.claims)
    cited_kept = cited_refs(kept)
    removed_by_checks = cited_by_model - cited_kept
    return Digest(
        subject=subject,
        claims=tuple(to_digest_claim(claim, item_by_ref) for claim in kept),
        sources=tuple(
            to_source(item)
            for item in items_sent
            if to_item_ref(item.item_id) in cited_kept
        ),
        items_not_retained_in_output=tuple(
            item.item_id
            for item in items_sent
            if to_item_ref(item.item_id) not in cited_by_model
        ),
        facts_checked=sum(fidelity.facts_checked for fidelity in fidelities),
        facts_found=sum(fidelity.facts_found for fidelity in fidelities),
        claims_removed=len(output.claims) - len(kept),
        items_removed_by_checks=tuple(
            item.item_id
            for item in items_sent
            if to_item_ref(item.item_id) in removed_by_checks
        ),
    )


def cited_refs(claims: Iterable[Claim]) -> set[str]:
    return {ref for claim in claims for ref in claim.item_ids}


def to_digest_claim(claim: Claim, item_by_ref: Mapping[str, WatchItem]) -> DigestClaim:
    return DigestClaim(
        text=claim.text,
        item_ids=tuple(item_by_ref[ref].item_id for ref in claim.item_ids),
    )


def to_source(item: WatchItem) -> DigestSource:
    url = (
        item.url
        if item.url is not None and item.url.startswith(SOURCE_URL_SCHEMES)
        else None
    )
    return DigestSource(
        item_id=item.item_id, kind=item.kind, title=item.source_title, url=url
    )
