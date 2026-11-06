# The .env of the main working tree, shared by its git worktrees.
ENV_FILE := $(dir $(shell git rev-parse --path-format=absolute --git-common-dir)).env

.PHONY: create-db collect import write-tops digest trend-report serve-data serve-ai openapi \
	test test-ai-api test-data-api test-etl test-cov

create-db:
	uv run --env-file $(ENV_FILE) kb create-db

collect:
	uv run --env-file $(ENV_FILE) kb collect

import:
	uv run --env-file $(ENV_FILE) kb import

write-tops:
	uv run --env-file $(ENV_FILE) kb write-tops

digest:
	uv run --env-file $(ENV_FILE) kb digest

trend-report:
	uv run --env-file $(ENV_FILE) kb trend-report

serve-data:
	uv run --env-file $(ENV_FILE) kb serve-data

serve-ai:
	uv run --env-file $(ENV_FILE) kb serve-ai

openapi:
	uv run --env-file $(ENV_FILE) kb openapi

# Tests, without --env-file, as in the CI: no key of the .env reaches the tests. Each run writes its
# pytest-html report to reports/, ignored by git, overwritten by the next run (0600, tests/conftest.py).
# The tests of the code shared by both APIs (core/), at the root of tests/: a new one is added here.
API_COMMON_TESTS := tests/test_api_methods.py tests/test_api_rate_limit.py tests/test_api_telemetry.py

test:
	uv run pytest --html=reports/$@.html --self-contained-html

test-ai-api:
	uv run pytest tests/ai_api --html=reports/$@.html --self-contained-html
	uv run pytest $(API_COMMON_TESTS) --html=reports/test-api-common.html --self-contained-html

test-data-api:
	uv run pytest tests/data_api --html=reports/$@.html --self-contained-html
	uv run pytest $(API_COMMON_TESTS) --html=reports/test-api-common.html --self-contained-html

test-etl:
	uv run pytest tests/etl --html=reports/$@.html --self-contained-html

# Coverage of the whole suite: the files below 100 % in the console, the full table in reports/coverage.md.
# pytest-cov does not create the folder of its report: made first, in 0700 as tests/conftest.py does.
test-cov:
	mkdir -p -m 700 reports
	uv run pytest --cov --cov-report=term-missing:skip-covered --cov-report=markdown:reports/coverage.md
