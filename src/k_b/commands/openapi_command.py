"""kb openapi: write the OpenAPI of the data API, versioned with the code."""

import json
import sys
from pathlib import Path

from k_b.commands.exit_codes import ExitCode
from k_b.data_api.app import create_app
from k_b.database.connection import DATABASE_FILE_NAME
from k_b.etl.raw_store import write_file_atomically

# Written from the root of the repository, which versions it.
OPENAPI_PATH = Path("docs") / "api" / "openapi-donnees.json"


def run_openapi() -> int:
    """Write the OpenAPI of the data API, versioned with the code (docs/specs-api.md)."""
    # Run from another folder, it would write a document the repository never sees.
    if not OPENAPI_PATH.parent.is_dir():
        print(
            f"error: {OPENAPI_PATH.parent} is not a directory of the current directory;"
            " run kb openapi at the root of the repository",
            file=sys.stderr,
        )
        return ExitCode.NOT_STARTED
    # The app is made without base nor key: its document does not depend on them.
    openapi = create_app(Path(DATABASE_FILE_NAME), {}).openapi()
    content = json.dumps(openapi, indent=2, ensure_ascii=False) + "\n"
    try:
        write_file_atomically(OPENAPI_PATH, content.encode())
    except OSError as error:
        print(
            f"error: {OPENAPI_PATH} not written: {type(error).__name__}",
            file=sys.stderr,
        )
        return ExitCode.FAILED
    print(f"OpenAPI written: {OPENAPI_PATH}")
    return ExitCode.SUCCEEDED
