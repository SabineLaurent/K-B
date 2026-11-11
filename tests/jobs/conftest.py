"""What the tests of the jobs share: the variables of a run online removed."""

import pytest
from exchange.storage_fakes import remove_online_variables


@pytest.fixture(autouse=True)
def no_online_variables(monkeypatch):
    remove_online_variables(monkeypatch)
