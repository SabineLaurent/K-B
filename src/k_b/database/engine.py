"""The engine of the items database: the type of the connection every module of K-B is given."""

import sqlite3

# The class of sqlite3 itself, not a wrapper: the SQLite path stays as it is.
Connection = sqlite3.Connection
