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

CREATE TABLE item (
    item_id        INTEGER PRIMARY KEY,
    source_code    TEXT NOT NULL REFERENCES source (source_code),
    source_item_id TEXT NOT NULL,
    title          TEXT NOT NULL,
    url            TEXT NOT NULL UNIQUE,
    published_at   TEXT
        CHECK (published_at IS strftime('%Y-%m-%dT%H:%M:%SZ', published_at)),
    revised_at     TEXT
        CHECK (revised_at IS strftime('%Y-%m-%dT%H:%M:%SZ', revised_at)),
    saved_at       TEXT
        CHECK (saved_at IS strftime('%Y-%m-%dT%H:%M:%SZ', saved_at)),
    summary        TEXT,
    raw_data_id    INTEGER NOT NULL REFERENCES raw_data (id),
    UNIQUE (source_code, source_item_id)
) STRICT;

CREATE INDEX item_published_at ON item (published_at);
CREATE INDEX item_saved_at ON item (saved_at);
CREATE INDEX item_raw_data_id ON item (raw_data_id);

CREATE TABLE author (
    author_id INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE
) STRICT;

CREATE TABLE item_author (
    item_id   INTEGER NOT NULL REFERENCES item (item_id) ON DELETE CASCADE,
    author_id INTEGER NOT NULL REFERENCES author (author_id) ON DELETE CASCADE,
    position  INTEGER NOT NULL CHECK (position >= 1),
    PRIMARY KEY (item_id, author_id),
    UNIQUE (item_id, position)
) STRICT;

CREATE INDEX item_author_author_id ON item_author (author_id);

CREATE TABLE highlight (
    highlight_id     INTEGER PRIMARY KEY,
    zotero_key       TEXT NOT NULL UNIQUE,
    text             TEXT NOT NULL,
    highlighted_at   TEXT NOT NULL
        CHECK (highlighted_at IS strftime('%Y-%m-%dT%H:%M:%SZ', highlighted_at)),
    item_id          INTEGER NOT NULL REFERENCES item (item_id) ON DELETE CASCADE
) STRICT;

CREATE INDEX highlight_item_id ON highlight (item_id);

CREATE TABLE repository (
    item_id         INTEGER PRIMARY KEY REFERENCES item (item_id) ON DELETE CASCADE,
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

-- A CVE is not unique: a CISA entry and a GitHub advisory of the same CVE are two items,
-- linked by their CVE (docs/stockage.md).
CREATE TABLE vulnerability (
    item_id INTEGER PRIMARY KEY REFERENCES item (item_id) ON DELETE CASCADE,
    cve     TEXT CHECK (cve GLOB 'CVE-[0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9]*')
) STRICT;

CREATE INDEX vulnerability_cve ON vulnerability (cve);
