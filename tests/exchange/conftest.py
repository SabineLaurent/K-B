"""What the tests of the exchange storage share with those of the jobs: the variables of a run online
removed."""

import pytest
from jobs.storage_fakes import remove_online_variables


@pytest.fixture(autouse=True)
def no_online_variables(monkeypatch):
    remove_online_variables(monkeypatch)
