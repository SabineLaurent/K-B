"""Download the AI security papers submitted to arXiv, as the API returns them."""

from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from k_b.arxiv_papers import count_papers, read_total_results
from k_b.http_download import download

API_URL = "https://export.arxiv.org/api/query"
# A page of 35 papers weighs 93 KB in 2026, about 2.7 KB a paper: 2,000 papers weigh 5.3 MB.
MAX_RESPONSE_BYTES = 6 * 1024 * 1024
# The API maximum. About 40 papers per window: one page holds them all.
PAPERS_PER_PAGE = 2000
# Papers both in cs.CR and cs.AI whose abstract has one of these keywords (decided in #6).
KEYWORDS = [
    "prompt injection",
    "jailbreak",
    "red teaming",
    "adversarial attack",
    "backdoor",
    "poisoning",
    "membership inference",
    "agent security",
]
# A paper is searchable only once announced, up to 3.5 days after its submission (Thursday
# 14:00 to Sunday 20:00, New York time), later on holidays. The window reaches back this far
# before the last collection so that late announcements are not lost; the overlap with the
# previous raw file is removed when merging, by arXiv identifier.
ANNOUNCEMENT_DELAY_MARGIN = timedelta(days=7)
# The first collection reaches back to the start of Sabine's training: 488 papers, 1.2 MB,
# measured on 2026-10-02.
FIRST_COLLECTION_START = datetime(2026, 5, 1, tzinfo=UTC)


# The name of its raw folders, written once: its instances and its kind use it.
FOLDER_PREFIX = "arxiv"


class ArxivSource:
    name = FOLDER_PREFIX
    extension = "xml"

    def fetch(self, last_collected_at: datetime | None) -> bytes | None:
        """Return the papers submitted since 7 days before last_collected_at; None if none.

        A first collection (last_collected_at is None) reaches back to FIRST_COLLECTION_START.
        """
        now = datetime.now(UTC)
        if last_collected_at is None:
            window_start = FIRST_COLLECTION_START
        else:
            window_start = last_collected_at - ANNOUNCEMENT_DELAY_MARGIN
        raw_response = download_papers(build_search_query(window_start, now))
        paper_count = count_papers(raw_response)
        total_results = read_total_results(raw_response)
        if total_results > paper_count:
            # Failing keeps the last collection date: the next collection asks again.
            raise ValueError(
                f"{total_results} papers found, only {paper_count} returned"
            )
        if paper_count == 0:
            return None
        return raw_response


def build_search_query(window_start: datetime, window_end: datetime) -> str:
    keywords = " OR ".join(
        f'abs:"{keyword}"' if " " in keyword else f"abs:{keyword}"
        for keyword in KEYWORDS
    )
    # The API reads these dates in GMT.
    window_start, window_end = window_start.astimezone(UTC), window_end.astimezone(UTC)
    submission_window = f"{window_start:%Y%m%d%H%M} TO {window_end:%Y%m%d%H%M}"
    return f"cat:cs.CR AND cat:cs.AI AND ({keywords}) AND submittedDate:[{submission_window}]"


def download_papers(search_query: str) -> bytes:
    parameters = {
        "search_query": search_query,
        "start": 0,
        "max_results": PAPERS_PER_PAGE,
        "sortBy": "submittedDate",
        "sortOrder": "ascending",
    }
    return download(f"{API_URL}?{urlencode(parameters)}", API_URL, MAX_RESPONSE_BYTES)
