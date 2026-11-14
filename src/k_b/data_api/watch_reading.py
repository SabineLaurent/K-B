"""The twins of the sheets of the tops (#559) and of the digests (#560) the data API reads in the
container watch: a folder listed by its prefix, a twin downloaded as listed and read again by the
closed schema of its kind, the listings and the last productions of each kind kept in memory a short
while.

The jobs write in watch: its names and its texts are inputs, never trusted, and never logged
(conventions.md, rule 3)."""

import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Literal, cast

from azure.core.paging import PageIterator
from azure.storage.blob import BlobProperties, ContainerClient
from pydantic import BaseModel, ValidationError

from k_b.core.config import (
    DATA_API_STORAGE_CONNECT_TIMEOUT_SECONDS,
    DATA_API_STORAGE_READ_TIMEOUT_SECONDS,
    MAX_DIGEST_TWIN_BYTES,
    MAX_WATCH_FOLDER_NAMES,
    MAX_WATCH_FOLDER_PAGES,
    MAX_WATCH_SHEET_BYTES,
    SHEET_TWIN_SUFFIX,
    TOPS_DIR_NAME,
    WATCH_CACHE_SECONDS,
    WATCH_CACHED_DIGESTS,
    WATCH_CACHED_TOPS,
    WATCH_CONTAINER,
)
from k_b.core.quoting import locate_first_error
from k_b.exchange.storage import (
    ExchangeStorageSettings,
    NamedFailureCredential,
    build_managed_identity_credential,
    build_transport,
    download_listed_version,
    naming_storage_errors,
    open_container_client,
)
from k_b.items import DigestProduction, TopProduction

# The day in the name of a twin, after the prefix of its folder: ASCII digits, matched whole
# (fullmatch), as $ would let a line feed end it.
TWIN_DAY = r"(?P<day>[0-9]{4}-[0-9]{2}-[0-9]{2})" + re.escape(SHEET_TWIN_SUFFIX)

type WatchReadingState = Literal[
    "watch_listing_too_long",
    "watch_production_refused",
    "watch_production_changed",
]


class WatchReadingError(Exception):
    """A reading of watch that stopped: its state, and what was measured, never a name nor a text
    of watch."""

    def __init__(self, state: WatchReadingState, measure: str) -> None:
        super().__init__(f"{state}: {measure}")
        self.state: WatchReadingState = state
        self.measure = measure


@dataclass(frozen=True)
class TwinKind[Production: BaseModel]:
    """A kind of twin in watch: the folder of its folders, its closed schema, what of a production
    names its folder and its day, the states of a production of another folder or day, its largest
    size, and how many productions read are kept."""

    parent: str
    schema: type[Production]
    read_folder: Callable[[Production], str]
    read_moment: Callable[[Production], datetime]
    folder_refusal: str
    day_refusal: str
    max_bytes: int
    kept_count: int

    def find_prefix(self, folder: str) -> str:
        """The prefix of the names of the twins of folder."""
        return f"{self.parent}{folder}/"


TOP_TWINS = TwinKind(
    parent=f"{TOPS_DIR_NAME}/",
    schema=TopProduction,
    read_folder=lambda production: production.top,
    read_moment=lambda production: production.ranked_at,
    folder_refusal="top_not_its_folder",
    day_refusal="ranked_at_not_its_day",
    max_bytes=MAX_WATCH_SHEET_BYTES,
    kept_count=WATCH_CACHED_TOPS,
)
# The folders of the subjects are at the root of watch, as in veille/ (post/digest_sheets.py).
DIGEST_TWINS = TwinKind(
    parent="",
    schema=DigestProduction,
    read_folder=lambda production: production.subject,
    read_moment=lambda production: production.until,
    folder_refusal="subject_not_its_folder",
    day_refusal="until_not_its_day",
    max_bytes=MAX_DIGEST_TWIN_BYTES,
    kept_count=WATCH_CACHED_DIGESTS,
)


@dataclass(frozen=True)
class ListedTwin:
    """A twin of the listing of a folder: its day and its blob, as listed."""

    day: date
    blob: BlobProperties


@dataclass(frozen=True)
class FolderListing:
    """The twins of a folder, the most recent first, and when they were listed."""

    twins: tuple[ListedTwin, ...]
    listed_at: float


@dataclass(frozen=True)
class TwinRefusal:
    """Why a twin is refused, kept as its production would be: it is never downloaded again."""

    reason: str


@dataclass(frozen=True)
class ProductionOfDay[Production: BaseModel]:
    """The production of a twin served, and its day."""

    day: date
    production: Production


class WatchReader:
    """The twins of watch, read through one client of the container; safe for the threads of the
    routes, its lock never held during a request to the storage."""

    def __init__(
        self,
        container_client: ContainerClient,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.container_client = container_client
        self.now = now
        self.monotonic = monotonic
        self.lock = threading.Lock()
        # By the prefix of a folder: the folders are a closed set, the tops and the subjects.
        self.listings: dict[str, FolderListing] = {}
        # Each kind with its own productions read, by name and etag, made at its first reading: a
        # production of a kind is of its schema, or its refusal (Any, as one dict holds every kind).
        self.productions: dict[TwinKind[Any], OrderedDict[tuple[str, str], Any]] = {}

    def list_days(self, kind: TwinKind[Any], folder: str) -> list[date]:
        """The days of the twins of the folder of kind, the most recent first, none after today
        (UTC)."""
        return [twin.day for twin in self.list_twins(kind, folder)]

    def read_production[Production: BaseModel](
        self, kind: TwinKind[Production], folder: str, day: date | None
    ) -> ProductionOfDay[Production] | None:
        """The twin of the folder of kind of day, or of its most recent day; None when it has
        none."""
        twins = self.list_twins(kind, folder)
        if day is None:
            twin = twins[0] if twins else None
        else:
            twin = next((twin for twin in twins if twin.day == day), None)
        if twin is None:
            return None
        return ProductionOfDay(twin.day, self.read_twin(kind, folder, twin))

    def list_twins(self, kind: TwinKind[Any], folder: str) -> list[ListedTwin]:
        """The twins of the listing of the folder kept, or listed again once WATCH_CACHE_SECONDS
        have passed; a twin of a day after today is left aside."""
        prefix = kind.find_prefix(folder)
        moment = self.monotonic()
        with self.lock:
            listing = self.listings.get(prefix)
        if listing is None or moment - listing.listed_at >= WATCH_CACHE_SECONDS:
            listing = FolderListing(
                list_folder_twins(self.container_client, prefix), moment
            )
            with self.lock:
                self.listings[prefix] = listing
        today = self.now().astimezone(UTC).date()
        return [twin for twin in listing.twins if twin.day <= today]

    def read_twin[Production: BaseModel](
        self, kind: TwinKind[Production], folder: str, twin: ListedTwin
    ) -> Production:
        """The production of the twin, read once for its name and its etag; a refusal raised as
        often as it is asked."""
        key = (twin.blob.name, twin.blob.etag)
        with self.lock:
            kept = self.productions.setdefault(kind, OrderedDict())
            production: Production | TwinRefusal | None = kept.get(key)
            if production is not None:
                kept.move_to_end(key)
        if production is None:
            production = self.download_twin(kind, folder, twin)
            with self.lock:
                kept[key] = production
                while len(kept) > kind.kept_count:
                    kept.popitem(last=False)
        if isinstance(production, TwinRefusal):
            raise WatchReadingError(
                "watch_production_refused",
                f"{folder} of {twin.day}: {production.reason}",
            )
        return production

    def download_twin[Production: BaseModel](
        self, kind: TwinKind[Production], folder: str, twin: ListedTwin
    ) -> Production | TwinRefusal:
        """The production of the twin as listed, or why it is refused; when it was changed or
        removed since the listing, the listing is forgotten and the request fails."""
        if twin.blob.size > kind.max_bytes:
            return TwinRefusal(
                f"twin_too_large, {twin.blob.size} bytes, maximum {kind.max_bytes}"
            )
        content = download_listed_version(
            self.container_client, twin.blob, kind.max_bytes
        )
        if content is None:
            with self.lock:
                self.listings.pop(kind.find_prefix(folder), None)
            raise WatchReadingError(
                "watch_production_changed", f"{folder} of {twin.day}"
            )
        return read_twin_production(content, kind, folder, twin.day)


def read_twin_production[Production: BaseModel](
    content: bytes, kind: TwinKind[Production], folder: str, day: date
) -> Production | TwinRefusal:
    """The production of a twin, refused out of the schema of its kind, of another folder than its
    own, or of another day (UTC) than its name."""
    try:
        production = kind.schema.model_validate_json(content)
    except ValidationError as error:
        return TwinRefusal(locate_first_error(error))
    if kind.read_folder(production) != folder:
        return TwinRefusal(kind.folder_refusal)
    if kind.read_moment(production).astimezone(UTC).date() != day:
        return TwinRefusal(kind.day_refusal)
    return production


def list_folder_twins(
    container_client: ContainerClient, prefix: str
) -> tuple[ListedTwin, ...]:
    """The twins of the folder of prefix, the most recent first; any other name is left aside."""
    twin_name = re.compile(re.escape(prefix) + TWIN_DAY)
    twins = []
    for blob in list_folder(container_client, prefix):
        match = twin_name.fullmatch(blob.name)
        day = None if match is None else read_day(match["day"])
        if day is not None:
            twins.append(ListedTwin(day, blob))
    return tuple(sorted(twins, key=lambda twin: twin.day, reverse=True))


def list_folder(container_client: ContainerClient, prefix: str) -> list[BlobProperties]:
    """The blobs whose name starts with prefix, the marker of a page cut short followed; beyond
    MAX_WATCH_FOLDER_NAMES names or MAX_WATCH_FOLDER_PAGES pages, WatchReadingError."""
    blobs: list[BlobProperties] = []
    with naming_storage_errors():
        # by_page gives the PageIterator of the SDK (azure/core/paging.py), typed as an iterator:
        # its continuation_token is the NextMarker of the last page read.
        pages = cast(
            PageIterator[BlobProperties],
            container_client.list_blobs(
                name_starts_with=prefix, results_per_page=MAX_WATCH_FOLDER_NAMES
            ).by_page(),
        )
        for _ in range(MAX_WATCH_FOLDER_PAGES):
            blobs.extend(next(pages))
            if len(blobs) > MAX_WATCH_FOLDER_NAMES:
                raise WatchReadingError(
                    "watch_listing_too_long",
                    f"more than {MAX_WATCH_FOLDER_NAMES} names",
                )
            if not pages.continuation_token:
                return blobs
    raise WatchReadingError(
        "watch_listing_too_long", f"more than {MAX_WATCH_FOLDER_PAGES} pages"
    )


def read_day(text: str) -> date | None:
    """The day of the calendar text names as date.isoformat writes it, or None."""
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return None
    return day if day.isoformat() == text else None


@contextmanager
def open_watch_reader(settings: ExchangeStorageSettings) -> Iterator[WatchReader]:
    """The reader of watch for kb serve-data, by the managed identity of the data API: shorter
    waits than a job, no retry of the pipeline, its clients closed at the end."""
    with (
        build_managed_identity_credential(
            settings.client_id,
            transport=build_transport(
                connect_timeout_seconds=DATA_API_STORAGE_CONNECT_TIMEOUT_SECONDS,
                read_timeout_seconds=DATA_API_STORAGE_READ_TIMEOUT_SECONDS,
            ),
            retry_total=0,
        ) as credential,
        open_container_client(
            settings.account_url,
            WATCH_CONTAINER,
            NamedFailureCredential(credential),
            transport=build_transport(
                connect_timeout_seconds=DATA_API_STORAGE_CONNECT_TIMEOUT_SECONDS,
                read_timeout_seconds=DATA_API_STORAGE_READ_TIMEOUT_SECONDS,
            ),
            retry_total=0,
        ) as container_client,
    ):
        yield WatchReader(container_client)
