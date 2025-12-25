PREFIX            := $(HOME)
SHELL_CONFIG_DIR  := $(PREFIX)/.config/shell
ALIAS_FILE        := aliases
TARGET_ALIAS_FILE := $(SHELL_CONFIG_DIR)/aliases

BASHRC := $(PREFIX)/.bashrc
ZSHRC  := $(PREFIX)/.zshrc

.PHONY: install refresh update sort list search add rename refactor export

# Usage:
#   make export a=gpull
#   make export a=gxa
export:
	@{ \
		if [ -z "$(a)" ]; then \
			echo "ERROR: missing alias name. Usage: make export a=<alias>"; \
			exit 2; \
		fi; \
	}
	@$(SCRIPTS_DIR)/export.sh "$(a)" $(ALIAS_FILE)

refactor:
	@python3 $(SCRIPTS_DIR)/refactor.py $(ALIAS_FILE)

# Usage:
#   make rename old=dc new=compose
rename:
	@{ \
		if [ -z "$(old)" ] || [ -z "$(new)" ]; then \
			echo "ERROR: missing args. Usage: make rename old=<old> new=<new>"; \
			exit 2; \
		fi; \
	}
	@$(SCRIPTS_DIR)/rename.sh "$(ALIAS_FILE)" "$(old)" "$(new)"

install:
	@echo ">>> Installing aliases"
	mkdir -p $(SHELL_CONFIG_DIR)
	cp $(ALIAS_FILE) $(TARGET_ALIAS_FILE)

	@echo ">>> Ensuring aliases are sourced in bash"
	grep -qxF '[ -f ~/.config/shell/aliases ] && . ~/.config/shell/aliases' $(BASHRC) \
		|| echo '[ -f ~/.config/shell/aliases ] && . ~/.config/shell/aliases' >> $(BASHRC)

	@echo ">>> Ensuring aliases are sourced in zsh"
	grep -qxF '[ -f ~/.config/shell/aliases ] && . ~/.config/shell/aliases' $(ZSHRC) \
		|| echo '[ -f ~/.config/shell/aliases ] && . ~/.config/shell/aliases' >> $(ZSHRC)

	@echo ">>> Aliases installed successfully"

refresh:
	@echo ">>> Aliases updated on disk"
	@echo ">>> Run one of the following in your shell:"
	@echo "    source ~/.config/shell/aliases"
	@echo "    exec $$SHELL"

update: install refresh

sort:
	@echo ">>> Sorting aliases alphabetically"
	@sort $(ALIAS_FILE) -o $(ALIAS_FILE)

SCRIPTS_DIR := scripts

list:
	@$(SCRIPTS_DIR)/list.sh $(ALIAS_FILE)

# Usage:
#   make search q=arc
search:
	@{ \
		if [ -z "$(q)" ]; then \
			echo "ERROR: missing query. Usage: make search q=<string>"; \
			exit 2; \
		fi; \
	}
	@$(SCRIPTS_DIR)/search.sh "$(q)" $(ALIAS_FILE)

add:
	@$(SCRIPTS_DIR)/add.sh $(ALIAS_FILE)