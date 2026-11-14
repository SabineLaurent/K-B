"""The twins of the sheets of the tops (#559) the data API reads in the container watch: the folder of
a top listed by its prefix, a twin downloaded as listed and read again by its closed schema, the
listings and the last productions kept in memory a short while.

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
from typing import Literal, cast

from azure.core.paging import PageIterator
from azure.storage.blob import BlobProperties, ContainerClient
from pydantic import ValidationError

from k_b.core.config import (
    DATA_API_STORAGE_CONNECT_TIMEOUT_SECONDS,
    DATA_API_STORAGE_READ_TIMEOUT_SECONDS,
    MAX_WATCH_FOLDER_NAMES,
    MAX_WATCH_FOLDER_PAGES,
    MAX_WATCH_SHEET_BYTES,
    SHEET_TWIN_SUFFIX,
    TOPS_DIR_NAME,
    WATCH_CACHE_SECONDS,
    WATCH_CACHED_PRODUCTIONS,
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
from k_b.items import TopName, TopProduction

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
class TopOfDay:
    """The twin of a top served, and its day."""

    day: date
    production: TopProduction


class WatchReader:
    """The twins of the tops in watch, read through one client of the container; safe for the
    threads of the routes, its lock never held during a request to the storage."""

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
        self.listings: dict[TopName, FolderListing] = {}
        self.productions: OrderedDict[tuple[str, str], TopProduction | TwinRefusal] = (
            OrderedDict()
        )

    def list_days(self, top: TopName) -> list[date]:
        """The days of the twins of top, the most recent first, none after today (UTC)."""
        return [twin.day for twin in self.list_twins(top)]

    def read_top(self, top: TopName, day: date | None) -> TopOfDay | None:
        """The twin of top of day, or of its most recent day; None when it has none."""
        twins = self.list_twins(top)
        if day is None:
            twin = twins[0] if twins else None
        else:
            twin = next((twin for twin in twins if twin.day == day), None)
        if twin is None:
            return None
        return TopOfDay(twin.day, self.read_twin(top, twin))

    def list_twins(self, top: TopName) -> list[ListedTwin]:
        """The twins of the listing of top kept, or listed again once WATCH_CACHE_SECONDS have
        passed; a twin of a day after today is left aside."""
        moment = self.monotonic()
        with self.lock:
            listing = self.listings.get(top)
        if listing is None or moment - listing.listed_at >= WATCH_CACHE_SECONDS:
            listing = FolderListing(
                list_folder_twins(self.container_client, top), moment
            )
            with self.lock:
                self.listings[top] = listing
        today = self.now().astimezone(UTC).date()
        return [twin for twin in listing.twins if twin.day <= today]

    def read_twin(self, top: TopName, twin: ListedTwin) -> TopProduction:
        """The production of the twin, read once for its name and its etag; a refusal raised as
        often as it is asked."""
        key = (twin.blob.name, twin.blob.etag)
        with self.lock:
            production = self.productions.get(key)
            if production is not None:
                self.productions.move_to_end(key)
        if production is None:
            production = self.download_twin(top, twin)
            with self.lock:
                self.productions[key] = production
                while len(self.productions) > WATCH_CACHED_PRODUCTIONS:
                    self.productions.popitem(last=False)
        if isinstance(production, TwinRefusal):
            raise WatchReadingError(
                "watch_production_refused", f"{top} of {twin.day}: {production.reason}"
            )
        return production

    def download_twin(
        self, top: TopName, twin: ListedTwin
    ) -> TopProduction | TwinRefusal:
        """The production of the twin as listed, or why it is refused; when it was changed or
        removed since the listing, the listing is forgotten and the request fails."""
        if twin.blob.size > MAX_WATCH_SHEET_BYTES:
            return TwinRefusal(
                f"twin_too_large, {twin.blob.size} bytes, maximum {MAX_WATCH_SHEET_BYTES}"
            )
        content = download_listed_version(
            self.container_client, twin.blob, MAX_WATCH_SHEET_BYTES
        )
        if content is None:
            with self.lock:
                self.listings.pop(top, None)
            raise WatchReadingError("watch_production_changed", f"{top} of {twin.day}")
        return read_twin_production(content, top, twin.day)


def read_twin_production(
    content: bytes, top: TopName, day: date
) -> TopProduction | TwinRefusal:
    """The production of a twin, refused out of its schema, of another top than its folder, or
    ranked another day (UTC) than its name."""
    try:
        production = TopProduction.model_validate_json(content)
    except ValidationError as error:
        return TwinRefusal(locate_first_error(error))
    if production.top != top:
        return TwinRefusal("top_not_its_folder")
    if production.ranked_at.astimezone(UTC).date() != day:
        return TwinRefusal("ranked_at_not_its_day")
    return production


def list_folder_twins(
    container_client: ContainerClient, top: TopName
) -> tuple[ListedTwin, ...]:
    """The twins of the folder of top, the most recent first; any other name is left aside."""
    prefix = f"{TOPS_DIR_NAME}/{top}/"
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
