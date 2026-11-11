"""The responses of GET /items and GET /items/{item_id}: the API's own models, never Item, so
that a field added to the reading is not served."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from k_b.items import ItemKind, RansomwareUse

# The dates the response names by where they come from: a date of K-B is the collection that saw
# a catalog row change, not a date of the source.
DATE_OF_K_B = "A date of K-B: the collection that saw the change."
EXPLOITED = (
    "The CVE is in the CISA KEV catalog, withdrawn since or not, the withdrawal in withdrawn_at;"
    " false says absent from the catalog, not unexploited; null without CVE."
)


class ListedItemSchema(BaseModel):
    id: int
    kind: ItemKind
    title: str
    # The date of since, as the base writes it: YYYY-MM-DDTHH:MM:SSZ.
    source_date: str
    url: str | None
    withdrawn_at: str | None = Field(
        description=f"Withdrawn from a catalog (vulnerability, Zotero entry). {DATE_OF_K_B}"
    )


# The item of the list of each kind: the six fields, then the identifiers of its kind
# (docs/specs-api.md, "Identifiants par sorte"). kind narrowed to one value tells pydantic, and
# the OpenAPI, which schema an item follows.


class ListedPaperSchema(ListedItemSchema):
    kind: Literal["paper"]
    arxiv_id: str


class ListedVulnerabilitySchema(ListedItemSchema):
    kind: Literal["vulnerability"]
    cve_id: str
    exploited: bool = Field(description=EXPLOITED)


class ListedReleaseSchema(ListedItemSchema):
    kind: Literal["release"]
    repository_name: str
    tag_name: str


class ListedAdvisorySchema(ListedItemSchema):
    kind: Literal["advisory"]
    ghsa_id: str
    cve_id: str | None
    exploited: bool | None = Field(description=EXPLOITED)
    packages: list[str]
    packages_truncated: bool = Field(
        description="Packages are left out: the list serves the first 10 of an advisory, its"
        " detail every one, and says false."
    )


class ListedNewsletterArticleSchema(ListedItemSchema):
    kind: Literal["newsletter_article"]
    edition: str = Field(
        description="The newsletter, such as ai; the day of the edition is source_date."
    )


class ListedZoteroEntrySchema(ListedItemSchema):
    kind: Literal["zotero_entry"]


class ListedClipSchema(ListedItemSchema):
    kind: Literal["clip"]


ListedItemOfKindSchema = Annotated[
    ListedPaperSchema
    | ListedVulnerabilitySchema
    | ListedReleaseSchema
    | ListedAdvisorySchema
    | ListedNewsletterArticleSchema
    | ListedZoteroEntrySchema
    | ListedClipSchema,
    Field(discriminator="kind"),
]


class ItemPageSchema(BaseModel):
    items: list[ListedItemOfKindSchema]
    # The offset of the next page; null on the last one, or beyond the bound of offset.
    next_offset: int | None
    total: int = Field(
        description="The items of kind, since and q, every page together: limit and offset do"
        " not change it."
    )


# The detail of each kind: the item of the list of its kind, then the fields of the detail.


class PaperDetailSchema(ListedPaperSchema):
    authors: list[str]
    summary: str
    arxiv_updated_at: str = Field(
        description="A date of arXiv: the last version of the paper."
    )


class VulnerabilityDetailSchema(ListedVulnerabilitySchema):
    description: str
    vendor: str
    product: str
    ransomware_use: RansomwareUse
    revised_at: str | None = Field(description=DATE_OF_K_B)


class ReleaseDetailSchema(ListedReleaseSchema):
    release_id: int
    body: str | None


class AdvisoryDetailSchema(ListedAdvisorySchema):
    """An advisory serves nothing beyond the list."""


class NewsletterArticleDetailSchema(ListedNewsletterArticleSchema):
    edition_date: str
    rank: int
    summary: str


class HighlightSchema(BaseModel):
    # Read from the highlight of the reading by its attributes: its key is not served.
    model_config = ConfigDict(from_attributes=True)

    text: str | None
    comment: str | None
    highlighted_at: str = Field(description="A date of Zotero: the highlight was made.")
    revised_at: str | None = Field(description=DATE_OF_K_B)
    withdrawn_at: str | None = Field(description=DATE_OF_K_B)


class ZoteroEntryDetailSchema(ListedZoteroEntrySchema):
    zotero_key: str
    item_type: str
    arxiv_id: str | None
    revised_at: str | None = Field(description=DATE_OF_K_B)
    # The withdrawn ones included, by date of creation.
    highlights: list[HighlightSchema]
    highlights_truncated: bool = Field(
        description="Highlights are left out: the first ones by date are served while their"
        " number and the length of their text and comment hold within the bounds of the detail."
    )


class ClipDetailSchema(ListedClipSchema):
    published_at: str | None = Field(
        description="A date of the page kept (published of Web Clipper): a day, at midnight"
        " UTC; null when the page gives none."
    )
    body: str = Field(
        description="The text kept, Markdown, as Web Clipper wrote it, cut at the bound of the"
        " detail."
    )
    body_truncated: bool = Field(
        description="The text is cut at the bound of the detail."
    )


ItemDetailSchema = Annotated[
    PaperDetailSchema
    | VulnerabilityDetailSchema
    | ReleaseDetailSchema
    | AdvisoryDetailSchema
    | NewsletterArticleDetailSchema
    | ZoteroEntryDetailSchema
    | ClipDetailSchema,
    Field(discriminator="kind"),
]
