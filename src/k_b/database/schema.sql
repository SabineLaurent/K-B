-- K-B: physical data model (MPD) of the items database, written for SQLite.
-- What is SQLite-specific, and its PostgreSQL equivalent: docs/stockage.md.
-- Conceptual and logical models: docs/merise/; the reasons behind them: docs/stockage.md and
-- docs/ADR/journal-decisions-projet.md.
-- Reference data (the sources) is in seed_sources.sql, run right after this script.
-- Every connection must run PRAGMA foreign_keys = ON: SQLite ignores foreign keys otherwise.
-- Dates are UTC text, 'YYYY-MM-DDTHH:MM:SSZ'; the CHECK refuses any other form.
-- A text a source writes has a maximum length, in characters, held twice: by the items and
-- the trend row (src/k_b/items.py) when the raw is read, and by a CHECK here; a test keeps both
-- equal. A JSON
-- list has a maximum count; the length of its elements is held by the items only, a CHECK
-- cannot go through them.

CREATE TABLE source (
    id               INTEGER PRIMARY KEY,
    source_code      TEXT NOT NULL UNIQUE,
    label            TEXT NOT NULL,
    source_type      TEXT NOT NULL
        CHECK (source_type IN ('web_service', 'file', 'scraping', 'database', 'big_data')),
    -- Each value has its retention in src/k_b/config.py; a test keeps both lists equal.
    acquisition_mode TEXT NOT NULL CHECK (acquisition_mode IN ('watch', 'library', 'wiki'))
) STRICT;

-- A raw data is one file of raw/, provided by one source; stream is the name of its source
-- folder (tldr_ai, arxiv_cscr_x_csai). It may contain no item.
CREATE TABLE raw_data (
    id            INTEGER PRIMARY KEY,
    source_id     INTEGER NOT NULL REFERENCES source (id),
    raw_file_path TEXT NOT NULL UNIQUE,
    stream        TEXT NOT NULL,
    collected_at  TEXT NOT NULL
        CHECK (collected_at IS strftime('%Y-%m-%dT%H:%M:%SZ', collected_at))
) STRICT;

CREATE INDEX raw_data_source_id ON raw_data (source_id);

-- ITEM is minimal (option D): what an item says is in its subtype or its reference table.
-- The kinds: docs/2026-10-07-clarification-modele.md, "Valeurs de kind"; a test keeps this list
-- equal to ItemKind in items.py.
CREATE TABLE item (
    id          INTEGER PRIMARY KEY,
    kind        TEXT NOT NULL
        CHECK (kind IN ('paper', 'vulnerability', 'newsletter_article', 'release', 'advisory')),
    raw_data_id INTEGER NOT NULL REFERENCES raw_data (id),
    -- The target of the (item_id, kind) foreign key of each subtype: an item has one subtype.
    UNIQUE (id, kind)
) STRICT;

CREATE INDEX item_raw_data_id ON item (raw_data_id);

-- A reference table: a paper exists once a source cites it; arXiv is the source of truth. Its
-- arXiv columns are filled if and only if item_id points to the arXiv item.
CREATE TABLE publication (
    id           INTEGER PRIMARY KEY,
    arxiv_id     TEXT NOT NULL UNIQUE CHECK (length(arxiv_id) <= 20),
    item_id      INTEGER UNIQUE REFERENCES item (id),
    title        TEXT CHECK (length(title) <= 500),
    summary      TEXT CHECK (length(summary) <= 5000),
    -- The names, in arXiv's order.
    authors      TEXT
        CHECK (json_valid(authors) AND json_type(authors) = 'array'
            AND json_array_length(authors) > 0)
        CHECK (json_array_length(authors) <= 1000),
    submitted_at TEXT
        CHECK (submitted_at IS strftime('%Y-%m-%dT%H:%M:%SZ', submitted_at)),
    revised_at   TEXT
        CHECK (revised_at IS strftime('%Y-%m-%dT%H:%M:%SZ', revised_at)),
    CHECK ((item_id IS NULL) = (title IS NULL)
        AND (item_id IS NULL) = (summary IS NULL)
        AND (item_id IS NULL) = (authors IS NULL)
        AND (item_id IS NULL) = (submitted_at IS NULL)
        AND (item_id IS NULL) = (revised_at IS NULL))
) STRICT;

CREATE TABLE highlight (
    highlight_id     INTEGER PRIMARY KEY,
    zotero_key       TEXT NOT NULL UNIQUE,
    text             TEXT NOT NULL,
    highlighted_at   TEXT NOT NULL
        CHECK (highlighted_at IS strftime('%Y-%m-%dT%H:%M:%SZ', highlighted_at)),
    item_id          INTEGER NOT NULL REFERENCES item (id) ON DELETE CASCADE
) STRICT;

CREATE INDEX highlight_item_id ON highlight (item_id);

-- Not an item (ADR of 2026-10-08): the repositories that gained the most stars and forks over a
-- window of 3 days, the 30 first by stars and the 30 first by forks together. One row per window
-- and per repository, produced by a raw result of gh_archive. News feed, by window: the first
-- ranking seen of a window is kept whole, so every row of a window has the same raw_data_id.
-- Each CHECK refuses nothing TrendRow (src/k_b/items.py) accepts; a test keeps both in step.
CREATE TABLE trend (
    id              INTEGER PRIMARY KEY,
    raw_data_id     INTEGER NOT NULL REFERENCES raw_data (id),
    -- The last day of the window: a day, written at midnight UTC.
    window_end      TEXT NOT NULL
        CHECK (window_end IS strftime('%Y-%m-%dT00:00:00Z', window_end)),
    -- repo.id of GitHub, and the last name seen in the window.
    repository_id   INTEGER NOT NULL CHECK (repository_id > 0),
    repository_name TEXT NOT NULL
        CHECK (repository_name GLOB '?*/?*')
        CHECK (length(repository_name) <= 255),
    stars_gained    INTEGER NOT NULL CHECK (stars_gained >= 0),
    forks_gained    INTEGER NOT NULL CHECK (forks_gained >= 0),
    UNIQUE (window_end, repository_id)
) STRICT;

CREATE INDEX trend_raw_data_id ON trend (raw_data_id);

-- A reference table: a CVE exists once a source cites it; CISA KEV is the source of truth, and
-- "exploited" reads item_id IS NOT NULL. Its KEV columns are filled if and only if item_id points
-- to the KEV item; revised_at and withdrawn_at may stay empty, but only with item_id.
CREATE TABLE vulnerability (
    id             INTEGER PRIMARY KEY,
    cve_id         TEXT NOT NULL UNIQUE
        CHECK (cve_id GLOB 'CVE-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]*')
        CHECK (length(cve_id) <= 20),
    item_id        INTEGER UNIQUE REFERENCES item (id),
    name           TEXT CHECK (length(name) <= 500),
    description    TEXT CHECK (length(description) <= 5000),
    vendor         TEXT CHECK (length(vendor) <= 200),
    product        TEXT CHECK (length(product) <= 500),
    -- dateAdded is a day: written at midnight UTC (docs/stockage.md).
    date_added     TEXT
        CHECK (date_added IS strftime('%Y-%m-%dT%H:%M:%SZ', date_added)),
    -- knownRansomwareCampaignUse.
    ransomware_use TEXT CHECK (ransomware_use IN ('Known', 'Unknown')),
    revised_at     TEXT
        CHECK (revised_at IS strftime('%Y-%m-%dT%H:%M:%SZ', revised_at)),
    withdrawn_at   TEXT
        CHECK (withdrawn_at IS strftime('%Y-%m-%dT%H:%M:%SZ', withdrawn_at)),
    CHECK ((item_id IS NULL) = (name IS NULL)
        AND (item_id IS NULL) = (description IS NULL)
        AND (item_id IS NULL) = (vendor IS NULL)
        AND (item_id IS NULL) = (product IS NULL)
        AND (item_id IS NULL) = (date_added IS NULL)
        AND (item_id IS NULL) = (ransomware_use IS NULL)
        AND (item_id IS NOT NULL OR (revised_at IS NULL AND withdrawn_at IS NULL)))
) STRICT;

-- A reference table, like source: the list of src/k_b/sources/tracked_repositories.py is the
-- source of truth; each import adds its repositories or updates them, and a repository removed
-- from the list keeps its row (#87). GitHub ignores the case of a repository name.
CREATE TABLE tracked_repository (
    id              INTEGER PRIMARY KEY,
    repository_name TEXT NOT NULL UNIQUE COLLATE NOCASE CHECK (repository_name GLOB '?*/?*'),
    -- The ecosystems of src/k_b/sources/github_advisories.py: a test keeps both lists equal.
    ecosystem       TEXT NOT NULL CHECK (ecosystem IN ('pip', 'npm')),
    -- The tracked packages, in the order of the list.
    packages        TEXT NOT NULL
        CHECK (json_valid(packages) AND json_type(packages) = 'array'
            AND json_array_length(packages) > 0)
) STRICT;

-- A subtype of item; GitHub is the source of truth, and the first version seen is kept.
-- kind NOT NULL: a NULL kind would pass its CHECK and skip the foreign key.
CREATE TABLE release (
    id                    INTEGER PRIMARY KEY,
    item_id               INTEGER NOT NULL UNIQUE,
    kind                  TEXT NOT NULL CHECK (kind = 'release'),
    tracked_repository_id INTEGER NOT NULL REFERENCES tracked_repository (id),
    release_id            INTEGER NOT NULL UNIQUE,
    tag_name              TEXT NOT NULL
        CHECK (length(tag_name) > 0)
        CHECK (length(tag_name) <= 255),
    -- As GitHub gives them: name may be NULL, body is Markdown.
    name                  TEXT CHECK (length(name) <= 255),
    body                  TEXT CHECK (length(body) <= 125000),
    published_at          TEXT NOT NULL
        CHECK (published_at IS strftime('%Y-%m-%dT%H:%M:%SZ', published_at)),
    -- html_url, kept as given: a tag may hold characters to encode.
    url                   TEXT NOT NULL
        CHECK (url GLOB 'https://*')
        CHECK (length(url) <= 2000),
    FOREIGN KEY (item_id, kind) REFERENCES item (id, kind)
) STRICT;

CREATE INDEX release_tracked_repository_id ON release (tracked_repository_id);

-- A subtype of item; GitHub is the source of truth, and the first version seen is kept. The CVE
-- it cites is created in vulnerability without its KEV columns when no source has cited it yet.
CREATE TABLE advisory (
    id               INTEGER PRIMARY KEY,
    item_id          INTEGER NOT NULL UNIQUE,
    kind             TEXT NOT NULL CHECK (kind = 'advisory'),
    ghsa_id          TEXT NOT NULL UNIQUE
        CHECK (ghsa_id GLOB 'GHSA-*')
        CHECK (length(ghsa_id) <= 19),
    vulnerability_id INTEGER REFERENCES vulnerability (id),
    summary          TEXT NOT NULL CHECK (length(summary) <= 1024),
    published_at     TEXT NOT NULL
        CHECK (published_at IS strftime('%Y-%m-%dT%H:%M:%SZ', published_at)),
    -- html_url, kept as given.
    url              TEXT NOT NULL
        CHECK (url GLOB 'https://*')
        CHECK (length(url) <= 2000),
    -- The affected packages, each once (decision of 2026-10-08: displayed, not filtered).
    packages         TEXT NOT NULL
        CHECK (json_valid(packages) AND json_type(packages) = 'array'
            AND json_array_length(packages) > 0)
        CHECK (json_array_length(packages) <= 100),
    FOREIGN KEY (item_id, kind) REFERENCES item (id, kind)
) STRICT;

CREATE INDEX advisory_vulnerability_id ON advisory (vulnerability_id);

-- A subtype of item; TLDR is the source of truth for its summary, and the first version seen is
-- kept. Its natural key is (edition, edition_date, rank): the URL is not unique, two editions
-- may summarize the same article (ADR of 2026-10-07).
CREATE TABLE newsletter_article (
    id             INTEGER PRIMARY KEY,
    item_id        INTEGER NOT NULL UNIQUE,
    kind           TEXT NOT NULL CHECK (kind = 'newsletter_article'),
    -- The slug of the edition, as in https://tldr.tech/<edition>/<YYYY-MM-DD>.
    edition        TEXT NOT NULL
        CHECK (edition <> '' AND edition NOT GLOB '*[^a-z]*')
        CHECK (length(edition) <= 20),
    -- The day of the edition, written at midnight UTC.
    edition_date   TEXT NOT NULL
        CHECK (edition_date IS strftime('%Y-%m-%dT%H:%M:%SZ', edition_date)),
    -- The position of the article in the edition page, from 1, sponsored entries and job
    -- offers counted.
    rank           INTEGER NOT NULL CHECK (rank >= 1),
    title          TEXT NOT NULL CHECK (length(title) <= 500),
    summary        TEXT NOT NULL CHECK (length(summary) <= 5000),
    -- The article summarized, without its utm_* parameters; not unique.
    url            TEXT NOT NULL
        CHECK (url GLOB 'https://*')
        CHECK (length(url) <= 2000),
    -- The paper the article cites: not filled yet (decision of 2026-10-12).
    publication_id INTEGER REFERENCES publication (id),
    UNIQUE (edition, edition_date, rank),
    FOREIGN KEY (item_id, kind) REFERENCES item (id, kind)
) STRICT;

CREATE INDEX newsletter_article_publication_id ON newsletter_article (publication_id);
