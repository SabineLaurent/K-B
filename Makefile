# The .env of the main working tree, shared by its git worktrees.
ENV_FILE := $(dir $(shell git rev-parse --path-format=absolute --git-common-dir)).env

.PHONY: create-db collect import write-tops digest trend-report serve-data serve-ai openapi \
	test-ai-api test-data-api test-etl

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

# Tests by group, without --env-file, as in the CI: no key of the .env reaches the tests.
# The tests of the code shared by both APIs (core/), at the root of tests/: a new one is added here.
API_COMMON_TESTS := tests/test_api_methods.py tests/test_api_rate_limit.py tests/test_api_telemetry.py

test-ai-api:
	uv run pytest tests/ai_api
	uv run pytest $(API_COMMON_TESTS)

test-data-api:
	uv run pytest tests/data_api
	uv run pytest $(API_COMMON_TESTS)

test-etl:
	uv run pytest tests/etl
