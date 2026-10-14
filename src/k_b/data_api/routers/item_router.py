"""GET /items: the list of the items and "what's new" (docs/specs-api.md, "GET /items")."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AfterValidator

from k_b.data_api.dependencies import Database
from k_b.data_api.errors import ERROR_RESPONSES
from k_b.data_api.schemas.item_schema import ItemPageSchema, ListedItemSchema
from k_b.database.reading import format_since, read_items
from k_b.items import ItemKind, NonEmptyText, UtcDatetime

# The bounds of the parameters (docs/specs-api.md, "Paramètres").
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_OFFSET = 10_000
MAX_SEARCH_LENGTH = 200


def check_since_can_be_read(since: datetime) -> datetime:
    """since as the reading compares it: rounded up to its second, it must remain a date
    (9999-12-31T23:59:59.5Z does not). A ValueError, which pydantic turns into a 422."""
    format_since(since)
    return since


Since = Annotated[UtcDatetime, AfterValidator(check_since_can_be_read)]

router = APIRouter()


@router.get("/items", responses=ERROR_RESPONSES)
def list_items(
    connection: Database,
    kind: Annotated[list[ItemKind] | None, Query()] = None,
    since: Annotated[Since | None, Query()] = None,
    q: Annotated[NonEmptyText | None, Query(max_length=MAX_SEARCH_LENGTH)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> ItemPageSchema:
    """A page of the items, the newest first by the date the source gives."""
    page = read_items(
        connection,
        limit=limit,
        offset=offset,
        kinds=kind or (),
        since=since,
        search_text=q,
    )
    return ItemPageSchema(
        items=[ListedItemSchema(**item._asdict()) for item in page.items],
        next_offset=bound_next_offset(page.next_offset),
    )


def bound_next_offset(next_offset: int | None) -> int | None:
    """None beyond the bound of offset: the client could not ask for that page (a 422)."""
    if next_offset is None or next_offset > MAX_OFFSET:
        return None
    return next_offset
