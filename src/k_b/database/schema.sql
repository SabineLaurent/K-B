-- K-B: physical data model (MPD) of the items database, written for SQLite.
-- What is SQLite-specific, and its PostgreSQL equivalent: docs/stockage.md.
-- Conceptual and logical models: docs/merise/; the reasons behind them: docs/stockage.md and
-- docs/ADR/journal-decisions-projet.md.
-- Reference data (the sources) is in seed_sources.sql, run right after this script.
-- Every connection must run PRAGMA foreign_keys = ON: SQLite ignores foreign keys otherwise.
-- Dates are UTC text, 'YYYY-MM-DDTHH:MM:SSZ'; the CHECK refuses any other form.

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
    raw_data_id INTEGER NOT NULL REFERENCES raw_data (id)
) STRICT;

CREATE INDEX item_raw_data_id ON item (raw_data_id);

-- A reference table: a paper exists once a source cites it; arXiv is the source of truth. Its
-- arXiv columns are filled if and only if item_id points to the arXiv item.
CREATE TABLE publication (
    id           INTEGER PRIMARY KEY,
    arxiv_id     TEXT NOT NULL UNIQUE,
    item_id      INTEGER UNIQUE REFERENCES item (id),
    title        TEXT,
    summary      TEXT,
    -- The names, in arXiv's order.
    authors      TEXT
        CHECK (json_valid(authors) AND json_type(authors) = 'array'
            AND json_array_length(authors) > 0),
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

CREATE TABLE repository (
    item_id         INTEGER PRIMARY KEY REFERENCES item (id) ON DELETE CASCADE,
    repository_name TEXT NOT NULL CHECK (repository_name GLOB '?*/?*')
) STRICT;

CREATE TABLE star_gain (
    item_id      INTEGER NOT NULL REFERENCES repository (item_id) ON DELETE CASCADE,
    window_end   TEXT NOT NULL
        CHECK (window_end IS strftime('%Y-%m-%dT%H:%M:%SZ', window_end)),
    stars_gained INTEGER NOT NULL CHECK (stars_gained >= 0),
    PRIMARY KEY (item_id, window_end)
) STRICT;

CREATE INDEX star_gain_window_end ON star_gain (window_end);

-- A reference table: a CVE exists once a source cites it; CISA KEV is the source of truth, and
-- "exploited" reads item_id IS NOT NULL. Its KEV columns are filled if and only if item_id points
-- to the KEV item; revised_at and withdrawn_at may stay empty, but only with item_id.
CREATE TABLE vulnerability (
    id             INTEGER PRIMARY KEY,
    cve_id         TEXT NOT NULL UNIQUE
        CHECK (cve_id GLOB 'CVE-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]*'),
    item_id        INTEGER UNIQUE REFERENCES item (id),
    name           TEXT,
    description    TEXT,
    vendor         TEXT,
    product        TEXT,
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
