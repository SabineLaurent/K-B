"""Mark as withdrawn what a state catalog no longer lists, while its raw file is written into
the base (stage 3).

Two kinds of raw file are a state catalog: a catalog of CISA KEV, and a Zotero extract, whose
entries and highlights are a state catalog too (decision of 2026-10-13). The rule is the load's,
not the source's: a source collects, it never decides what the base keeps.

Each function takes the file read and the row that registers it, and returns how many rows it
marked; the SQL of a withdrawal is in the writer of the kind (database/writers/).
"""

import sqlite3

from k_b.database.writing import (
    mark_withdrawn_vulnerabilities_not_in,
    mark_withdrawn_zotero_rows_not_in,
)
from k_b.etl.raw_files import RawFile


def mark_withdrawn_vulnerabilities(
    connection: sqlite3.Connection, raw_file: RawFile, raw_data_id: int
) -> int:
    """Mark as withdrawn the CVE a catalog no longer lists (vulnerability_writer.py);
    return how many.

    Only a file of vulnerabilities, all of its entries read: a rejected row is in the catalog,
    not absent from it.
    """
    present_cve_ids = [
        item.cve
        for item in raw_file.items
        if item.kind == "vulnerability" and item.cve is not None
    ]
    if not present_cve_ids or raw_file.rejection_count:
        return 0
    return mark_withdrawn_vulnerabilities_not_in(
        connection,
        raw_file.source_code,
        raw_file.collected_at,
        raw_data_id,
        present_cve_ids,
    )


def mark_withdrawn_zotero_rows(
    connection: sqlite3.Connection, raw_file: RawFile, raw_data_id: int
) -> int:
    """Mark as withdrawn the entries and the highlights an extract no longer lists
    (zotero_entry_writer.py); return how many.

    The same conditions as for a catalog of CISA KEV: an extract with a rejected entry, or
    without entry, withdraws nothing.
    """
    entries = [item for item in raw_file.items if item.kind == "zotero_entry"]
    if not entries or raw_file.rejection_count:
        return 0
    return mark_withdrawn_zotero_rows_not_in(
        connection, raw_file.source_code, raw_file.collected_at, raw_data_id, entries
    )
