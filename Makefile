.PHONY: create-db collect import write-tops digest serve-data serve-ai openapi

create-db:
	uv run --env-file .env kb create-db

collect:
	uv run --env-file .env kb collect

import:
	uv run --env-file .env kb import

write-tops:
	uv run --env-file .env kb write-tops

digest:
	uv run --env-file .env kb digest

serve-data:
	uv run --env-file .env kb serve-data

serve-ai:
	uv run --env-file .env kb serve-ai

openapi:
	uv run --env-file .env kb openapi
