"""The PostgreSQL branch of the engine: the placeholders translated, every SQL text of database/
through the translator, the state of a transaction, the errors of an entry refused alone, the
lock of the writers, and the token of the identity as the password of each new connection."""

import ast
import re
import threading
from pathlib import Path

import psycopg
import pytest
from azure.core.credentials import AccessToken
from azure.core.exceptions import ClientAuthenticationError
from commands.test_postgresql_errors_in_logs import OUT_OF_RANGE_MARKER

import k_b
from k_b.database import entra, postgresql
from k_b.database.creation import (
    UnsuitableDatabaseError,
    check_database_settings,
    create_database,
)
from k_b.database.engine import connect_database, lock_for_writing
from k_b.database.entra import POSTGRESQL_TOKEN_SCOPE
from k_b.database.errors import ENGINE_ERRORS, describe_engine_error
from k_b.database.location import PostgresUrl, RefusedDatabaseUrlError
from k_b.database.postgresql import DatabaseNoTokenError, translate_placeholders
from k_b.database.savepoint import EntryRefusedError, write_in_savepoint

DATABASE_DIR = Path(k_b.__file__).parent / "database"
# The first word of an SQL text of K-B: a docstring or a message never starts with one in capitals.
SQL_START = re.compile(
    r"\s*(SELECT|INSERT|UPDATE|DELETE|WITH|SAVEPOINT|RELEASE|ROLLBACK)\b"
)
# The rule of SQLAlchemy 2.0.55 for a named placeholder, the one the translator follows.
NAMED_PLACEHOLDER = re.compile(r"(?<![:\w\\]):(\w+)(?![:\w])")


@pytest.mark.parametrize(
    ("sql", "translated"),
    [
        ("SELECT id FROM item WHERE id = ?", "SELECT id FROM item WHERE id = %s"),
        (
            "UPDATE clip SET title = :title WHERE item_id = :item_id",
            "UPDATE clip SET title = %(title)s WHERE item_id = %(item_id)s",
        ),
        # A cast, a name after a word, a name followed by a colon, an escaped colon: no
        # placeholder, as for SQLAlchemy.
        ("SELECT x::text", "SELECT x::text"),
        ("SELECT 'T09:30:00Z'", "SELECT 'T09:30:00Z'"),
        ("SELECT :a:b", "SELECT :a:b"),
        ("SELECT \\:name", "SELECT \\:name"),
        # A % is doubled: psycopg reads %s and %(name)s.
        ("SELECT 'a%' WHERE x = ?", "SELECT 'a%%' WHERE x = %s"),
        ("SELECT :same, :same", "SELECT %(same)s, %(same)s"),
    ],
)
def test_the_placeholders_of_sqlite3_become_those_of_psycopg(sql, translated):
    assert translate_placeholders(sql) == translated


def list_sql_texts():
    """Every SQL text of database/, as written in its module: a constant or the text given to
    execute(), found in the syntax tree; a text the code builds by .format keeps its {…}.

    The pieces of an f-string are left out: they are not texts, and the whole, made of constants
    of its module, is run on PostgreSQL by the tests of the reading (fixture engine)."""
    texts = []
    for path in sorted(DATABASE_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text())
        pieces = {
            piece
            for node in ast.walk(tree)
            if isinstance(node, ast.JoinedStr)
            for piece in node.values
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and SQL_START.match(node.value)
                and node not in pieces
            ):
                texts.append(pytest.param(node.value, id=f"{path.name}:{node.lineno}"))
    return texts


SQL_TEXTS = list_sql_texts()


@pytest.mark.parametrize(
    "settings",
    [
        ("UTF8", "c", "C", "en_US.UTF-8", None),
        ("UTF8", "i", "C", "C", "und"),
        ("UTF8", "b", None, None, "C.UTF-8"),
    ],
)
def test_a_base_out_of_the_collation_c_is_refused_with_each_setting_read(settings):
    _, provider, collation, character_type, locale = settings

    with pytest.raises(UnsuitableDatabaseError) as raised:
        check_database_settings(settings)

    assert str(raised.value) == (
        "the PostgreSQL base is not in the collation C:"
        f" datlocprovider {provider!r}, datcollate {collation!r},"
        f" datctype {character_type!r}, datlocale {locale!r}"
    )


def test_the_sql_texts_of_database_are_found():
    # The writers, the purge, the reading, the savepoint and the lock: enough to be the code.
    assert len(SQL_TEXTS) > 60


@pytest.mark.parametrize("sql", SQL_TEXTS)
def test_each_sql_text_of_database_passes_through_the_translator(sql):
    translated = translate_placeholders(sql)

    # One style of placeholder per text: psycopg refuses %s and %(name)s together.
    assert not ("?" in sql and NAMED_PLACEHOLDER.search(sql))
    assert "?" not in translated
    assert set(re.findall(r"%\((\w+)\)s", translated)) == set(
        NAMED_PLACEHOLDER.findall(sql)
    )
    assert translated.count("%s") == sql.count("?")
    # Every other % is doubled: psycopg reads none of them as a placeholder.
    assert "%" not in re.sub(r"%%|%s|%\(\w+\)s", "", translated)


def number_placeholders(translated):
    """The SQL as PostgreSQL reads it once psycopg has bound it: $1, $2… in place of %s, one number
    per name in place of %(name)s, and %% back to %."""
    numbers = {}
    positions = iter(range(1, len(translated) + 1))

    def number(match):
        if match.group(1) is None:
            return f"${next(positions)}"
        return f"${numbers.setdefault(match.group(1), len(numbers) + 1)}"

    return re.sub(r"%s|%\((\w+)\)s", number, translated).replace("%%", "%")


@pytest.mark.postgresql
def test_each_sql_text_of_database_is_accepted_by_postgresql(postgresql_base):
    """Prepared, not run: PostgreSQL parses each statement and deduces the type of each
    parameter, as for an import, without a row; a text built by .format is left out."""
    create_database(postgresql_base)
    connection = psycopg.connect(postgresql_base.value)
    try:
        refused = {}
        for parameter in SQL_TEXTS:
            (sql,) = parameter.values
            if "{" in sql:
                continue
            query = number_placeholders(translate_placeholders(sql))
            result = connection.pgconn.prepare(b"", query.encode())
            if result.error_message:
                refused[parameter.id] = result.error_message.decode().splitlines()[0]
    finally:
        connection.close()

    assert refused == {}


SCHEMA = """
CREATE TABLE parent (id bigint PRIMARY KEY);
CREATE TABLE note (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    text text NOT NULL UNIQUE CHECK (length(text) > 0),
    rank bigint CHECK (rank > 0),
    parent_id bigint REFERENCES parent (id)
);
CREATE TABLE note_link (
    note_id bigint NOT NULL REFERENCES note (id),
    parent_id bigint NOT NULL REFERENCES parent (id),
    PRIMARY KEY (note_id, parent_id)
);
"""

on_postgresql = pytest.mark.postgresql


@pytest.fixture
def connection(postgresql_base):
    connection = connect_database(postgresql_base)
    connection.executescript(SCHEMA)
    connection.commit()
    # The import opens its transaction with its first write, before any savepoint.
    connection.execute("INSERT INTO note (text) VALUES ('before')")
    yield connection
    connection.close()


def read_notes(connection):
    return [text for (text,) in connection.execute("SELECT text FROM note ORDER BY id")]


@on_postgresql
def test_a_connection_is_in_a_transaction_while_it_writes_and_after_an_error(
    postgresql_base,
):
    connection = connect_database(postgresql_base)
    try:
        assert not connection.in_transaction
        connection.execute("SELECT 1")
        assert connection.in_transaction
        with pytest.raises(psycopg.errors.DivisionByZero):
            connection.execute("SELECT 1 / 0")
        # INERROR: the transaction is still open, to be undone.
        assert connection.in_transaction
        connection.rollback()
        assert not connection.in_transaction
    finally:
        connection.close()


# The errors due to the entry (conventions.md, rule 1), each with its description: its class, its
# SQLSTATE and the names diag gives, never a message of PostgreSQL, which may quote the value
# refused (22003), nor its DETAIL, which quotes the row.
@on_postgresql
@pytest.mark.parametrize(
    ("statement", "parameters", "description"),
    [
        (
            "INSERT INTO note (text) VALUES (?)",
            ("",),
            "CheckViolation 23514: table 'note', constraint 'note_text_check'",
        ),
        (
            "INSERT INTO note (text) VALUES (?)",
            ("before",),
            "UniqueViolation 23505: table 'note', constraint 'note_text_key'",
        ),
        (
            "INSERT INTO note (text) VALUES (?)",
            (None,),
            "NotNullViolation 23502: table 'note', column 'text'",
        ),
        (
            "INSERT INTO note (text, rank) VALUES ('ranked', ?)",
            (2**63,),
            "NumericValueOutOfRange 22003",
        ),
        (
            "INSERT INTO note (text, rank) VALUES ('ranked', CAST(? AS bigint))",
            (OUT_OF_RANGE_MARKER,),
            "NumericValueOutOfRange 22003",
        ),
        (
            "INSERT INTO note (text) VALUES (?)",
            ("ab\ud800",),
            "UnicodeEncodeError: surrogates not allowed at position 2",
        ),
    ],
    ids=[
        "23514",
        "23505",
        "23502",
        "22003",
        "22003 quoting its value",
        "lone surrogate",
    ],
)
def test_an_error_due_to_the_entry_is_refused_alone_and_the_import_goes_on(
    connection, statement, parameters, description
):
    with pytest.raises(EntryRefusedError) as refusal, write_in_savepoint(connection):
        connection.execute(statement, parameters)

    assert str(refusal.value) == description
    # PostgreSQL left INERROR for the savepoint: the next entry is written, and kept.
    with write_in_savepoint(connection):
        connection.execute("INSERT INTO note (text) VALUES ('after')")
    connection.commit()
    assert read_notes(connection) == ["before", "after"]


# Not due to the entry: a writer or a schema that does not match the base. They stop the import,
# raised unchanged, as SQLITE_CONSTRAINT_PRIMARYKEY and SQLITE_CONSTRAINT_FOREIGNKEY do.
@on_postgresql
@pytest.mark.parametrize(
    ("statement", "error_class"),
    [
        (
            "INSERT INTO note (text, parent_id) VALUES ('orphan', 99)",
            psycopg.errors.ForeignKeyViolation,
        ),
        (
            "INSERT INTO note (id, text) VALUES (1, 'same id')",
            psycopg.errors.UniqueViolation,
        ),
    ],
    ids=["foreign key", "primary key"],
)
def test_another_constraint_of_the_base_is_undone_and_raised_unchanged(
    connection, statement, error_class
):
    with pytest.raises(error_class), write_in_savepoint(connection):
        connection.execute(statement)

    assert read_notes(connection) == ["before"]


@on_postgresql
def test_a_primary_key_of_two_columns_refused_is_not_an_entry_refusal(connection):
    connection.execute("INSERT INTO parent (id) VALUES (1)")
    connection.execute("INSERT INTO note_link (note_id, parent_id) VALUES (1, 1)")

    with pytest.raises(psycopg.errors.UniqueViolation), write_in_savepoint(connection):
        connection.execute("INSERT INTO note_link (note_id, parent_id) VALUES (1, 1)")


@on_postgresql
def test_a_writer_waits_for_the_lock_of_another_then_fails_after_its_timeout(
    postgresql_base, monkeypatch
):
    monkeypatch.setattr(postgresql, "DATABASE_LOCK_TIMEOUT_SECONDS", 0.2)
    holder = connect_database(postgresql_base)
    waiter = connect_database(postgresql_base)
    try:
        lock_for_writing(holder)

        with pytest.raises(psycopg.errors.LockNotAvailable):
            lock_for_writing(waiter)
        waiter.rollback()

        # Once the holder ends its transaction, the lock is free.
        holder.commit()
        lock_for_writing(waiter)
    finally:
        holder.close()
        waiter.close()


@on_postgresql
def test_a_writer_gets_the_lock_once_the_other_commits(postgresql_base):
    holder = connect_database(postgresql_base)
    waiter = connect_database(postgresql_base)
    try:
        lock_for_writing(holder)
        locked = threading.Event()

        def lock_then_tell():
            lock_for_writing(waiter)
            locked.set()

        thread = threading.Thread(target=lock_then_tell)
        thread.start()
        assert not locked.wait(0.5)
        holder.commit()
        thread.join(5)
        assert locked.is_set()
    finally:
        holder.close()
        waiter.close()


# The client id of a user-assigned identity, as Azure gives it.
CLIENT_ID = "6f1c2a9e-3b4d-4e5f-8a7b-9c0d1e2f3a4b"
ENTRA_URL = "postgresql://id-kb-data-api@127.0.0.1:1/kb?sslmode=verify-full"
NO_VERIFY_FULL = "KB_DATABASE_URL does not set sslmode=verify-full, which KB_DATABASE_AUTH entra asks for"


class TokenSequence:
    """A credential of the test: each token it gives is a new one, and each scope asked is kept."""

    def __init__(self):
        self.scopes = []

    def get_token(self, *scopes, **kwargs):
        self.scopes.append(scopes)
        return AccessToken(f"token-{len(self.scopes)}", 4102444800)


@pytest.fixture
def token_sequence(monkeypatch):
    """The credential each connection under Entra gets."""
    credential = TokenSequence()
    monkeypatch.setattr(
        entra, "build_database_credential", lambda client_id: credential
    )
    return credential


@pytest.fixture
def without_tls(monkeypatch):
    """The test server has no TLS, and verify-full would refuse it: the check of the URL is left
    out, so that what libpq receives can be read; the server, in trust, checks no token."""
    monkeypatch.setattr(postgresql, "find_entra_url_refusal", lambda settings: None)


@pytest.mark.parametrize(
    ("url", "refusal"),
    [
        (
            "postgresql://id-kb-data-api@db.example/kb",
            NO_VERIFY_FULL,
        ),
        (
            "postgresql://id-kb-data-api@db.example/kb?sslmode=require",
            NO_VERIFY_FULL,
        ),
        (
            "postgresql://id-kb-data-api:S3cret@db.example/kb?sslmode=verify-full",
            "KB_DATABASE_URL holds a password, which KB_DATABASE_AUTH entra refuses",
        ),
        (
            "postgresql://id-kb-data-api@db.example/kb?sslmode=verify-full&password=S3cret",
            "KB_DATABASE_URL holds a password, which KB_DATABASE_AUTH entra refuses",
        ),
    ],
    ids=["no sslmode", "sslmode require", "password", "password parameter"],
)
@pytest.mark.parametrize(
    "open_base",
    [
        postgresql.connect_postgresql,
        lambda location: postgresql.open_reading_pool(location, 5).__enter__(),
    ],
    ids=["connection", "pool"],
)
def test_under_entra_a_url_that_could_give_the_token_away_is_refused_before_any_token(
    token_sequence, url, refusal, open_base
):
    with pytest.raises(RefusedDatabaseUrlError) as raised:
        open_base(PostgresUrl(url, entra_client_id=CLIENT_ID))

    assert str(raised.value) == refusal
    assert token_sequence.scopes == []


def test_under_entra_an_identity_without_token_is_a_named_error_of_the_base(
    monkeypatch,
):
    class RefusingCredential:
        def get_token(self, *scopes, **kwargs):
            raise ClientAuthenticationError("refused by the endpoint")

    monkeypatch.setattr(
        entra, "build_database_credential", lambda client_id: RefusingCredential()
    )

    with pytest.raises(DatabaseNoTokenError) as raised:
        postgresql.connect_postgresql(PostgresUrl(ENTRA_URL, entra_client_id=CLIENT_ID))

    assert isinstance(raised.value, ENGINE_ERRORS)
    assert describe_engine_error(raised.value) == "DatabaseNoTokenError"
    assert raised.value.__cause__ is None
    assert raised.value.__suppress_context__


@pytest.mark.postgresql
def test_under_entra_each_connection_gets_a_token_of_the_base_as_its_password(
    postgresql_base, token_sequence, without_tls
):
    location = PostgresUrl(postgresql_base.value, entra_client_id=CLIENT_ID)

    connections = [postgresql.connect_postgresql(location) for _ in range(2)]
    try:
        passwords = [connection._connection.info.password for connection in connections]
    finally:
        for connection in connections:
            connection.close()

    assert passwords == ["token-1", "token-2"]
    assert token_sequence.scopes == [(POSTGRESQL_TOKEN_SCOPE,)] * 2


@pytest.mark.postgresql
def test_under_entra_the_pool_asks_a_token_for_each_connection_it_opens(
    postgresql_base, token_sequence, without_tls
):
    location = PostgresUrl(postgresql_base.value, entra_client_id=CLIENT_ID)

    with (
        postgresql.open_reading_pool(location, 5) as pool,
        pool.connection() as first,
        pool.connection() as second,
    ):
        passwords = {first.info.password, second.info.password}

    assert len(passwords) == 2
    assert passwords <= {f"token-{n}" for n in range(1, len(token_sequence.scopes) + 1)}


@pytest.mark.postgresql
def test_without_entra_a_connection_sends_no_password_of_k_b(
    postgresql_base, monkeypatch
):
    monkeypatch.setattr(
        entra, "build_database_credential", lambda client_id: pytest.fail("no token")
    )

    connection = postgresql.connect_postgresql(postgresql_base)
    try:
        # libpq gives an empty text for a password it was not given.
        assert connection._connection.info.password == ""
    finally:
        connection.close()
