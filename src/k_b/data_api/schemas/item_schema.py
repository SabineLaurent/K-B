"""The response of GET /items: the fields of the list, and only them (docs/specs-api.md,
"Réponse"). The API's own models, never Item: a field added to the reading is not served."""

from pydantic import BaseModel

from k_b.items import ItemKind


class ListedItemSchema(BaseModel):
    id: int
    kind: ItemKind
    title: str
    # The date of since, as the base writes it: YYYY-MM-DDTHH:MM:SSZ.
    source_date: str
    url: str | None
    withdrawn_at: str | None


class ItemPageSchema(BaseModel):
    items: list[ListedItemSchema]
    # The offset of the next page; null on the last one, or beyond the bound of offset.
    next_offset: int | None
