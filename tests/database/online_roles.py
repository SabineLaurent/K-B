"""The roles of the base online, as the tests give them to the test server: those of the managed
identities, which create-principals.sql creates on Azure, and those grant-roles.sql creates."""

from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from k_b.database.location import PostgresUrl

# The administration of the base online, run as Sabine runs it on Azure (infra/README.md).
GRANT_ROLES_SCRIPT = (
    Path(__file__).parents[2] / "infra" / "postgresql" / "grant-roles.sql"
)
# The roles of the managed identities, which create-principals.sql creates on Azure: login roles of
# the test server here, which trusts them without a token.
MIGRATE_DATABASE_ROLE = "id-kb-migrate-database"
DATA_API_ROLE = "id-kb-data-api"
DAILY_ROUTINE_ROLE = "id-kb-daily-routine"
IDENTITY_ROLES = (MIGRATE_DATABASE_ROLE, DATA_API_ROLE, DAILY_ROUTINE_ROLE)
# The roles grant-roles.sql creates; kb migrate-database grants them the tables.
GROUP_ROLES = ("kb_reader", "kb_writer")


def as_role(location, role):
    """The URL of the base of location, for another role of the test server."""
    parts = urlsplit(location.value)
    host = parts.netloc.rpartition("@")[2]
    return PostgresUrl(urlunsplit(parts._replace(netloc=f"{role}@{host}")))
