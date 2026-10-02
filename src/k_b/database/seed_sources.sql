-- K-B: reference data of the items database, run right after schema.sql.
-- Safe to run again: a source already present is left as is.

INSERT INTO source (source_code, label, source_type) VALUES
    ('github',     'API GitHub',              'web_service'),
    ('arxiv',      'API arXiv',               'web_service'),
    ('cisa_kev',   'Catalogue CISA KEV',      'file'),
    ('clipper',    'Obsidian Web Clipper',    'file'),
    ('tldr',       'tldr.tech',               'scraping'),
    ('zotero',     'Zotero',                  'database'),
    ('gh_archive', 'GH Archive sur BigQuery', 'big_data')
ON CONFLICT (source_code) DO NOTHING;
