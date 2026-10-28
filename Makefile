# Shortcuts for the commands of kb, run from the root of the repository, beside .env.
# ESSAI=1 adds .env.essai after .env: its values win (the test base and vault).
ENV_FILES := --env-file .env
ifdef ESSAI
ENV_FILES += --env-file .env.essai
endif
KB := uv run $(ENV_FILES) kb

COMMANDS := create-db collect import write-tops digest serve-data serve-ai
.PHONY: $(COMMANDS)

$(COMMANDS):
	$(KB) $@
