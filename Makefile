PREFIX            := $(HOME)
SHELL_CONFIG_DIR  := $(PREFIX)/.config/shell
ALIAS_FILE        := aliases
TARGET_ALIAS_FILE := $(SHELL_CONFIG_DIR)/aliases

BASHRC := $(PREFIX)/.bashrc
ZSHRC  := $(PREFIX)/.zshrc

.PHONY: install refresh update sort list search

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

list:
	@echo ">>> Listing aliases from $(ALIAS_FILE)"
	@printf "%-20s | %-45s | %s\n" "alias" "command" "comment"
	@printf "%-20s-+-%-45s-+-%s\n" "--------------------" "---------------------------------------------" "------------------------------"
	@awk '\
		BEGIN { OFS=" | " } \
		/^[[:space:]]*alias[[:space:]]+/ { \
			line=$$0; \
			comment=""; \
			if (match(line, /[[:space:]]*#[[:space:]]*(.*)$$/, m)) { comment=m[1]; sub(/[[:space:]]*#[[:space:]]*.*/, "", line); } \
			sub(/^[[:space:]]*alias[[:space:]]+/, "", line); \
			name=line; sub(/=.*/, "", name); \
			cmd=line; sub(/^[^=]*=/, "", cmd); \
			gsub(/^[[:space:]]+|[[:space:]]+$$/, "", cmd); \
			gsub(/^'\''|'\''$$/, "", cmd); \
			gsub(/^"|"$$/, "", cmd); \
			printf "%-20s | %-45s | %s\n", name, cmd, comment; \
		} \
	' $(ALIAS_FILE)

# Usage:
#   make search q=arc
#   make search q=docker
search:
	@{ \
		if [ -z "$(q)" ]; then \
			echo "ERROR: missing query. Usage: make search q=<string>"; \
			exit 2; \
		fi; \
	}
	@echo ">>> Searching aliases for: $(q)"
	@printf "%-20s | %-45s | %s\n" "alias" "command" "comment"
	@printf "%-20s-+-%-45s-+-%s\n" "--------------------" "---------------------------------------------" "------------------------------"
	@awk -v q="$(q)" '\
		BEGIN { OFS=" | "; ql=tolower(q) } \
		/^[[:space:]]*alias[[:space:]]+/ { \
			orig=$$0; \
			if (index(tolower(orig), ql) == 0) next; \
			line=orig; \
			comment=""; \
			if (match(line, /[[:space:]]*#[[:space:]]*(.*)$$/, m)) { comment=m[1]; sub(/[[:space:]]*#[[:space:]]*.*/, "", line); } \
			sub(/^[[:space:]]*alias[[:space:]]+/, "", line); \
			name=line; sub(/=.*/, "", name); \
			cmd=line; sub(/^[^=]*=/, "", cmd); \
			gsub(/^[[:space:]]+|[[:space:]]+$$/, "", cmd); \
			gsub(/^'\''|'\''$$/, "", cmd); \
			gsub(/^"|"$$/, "", cmd); \
			printf "%-20s | %-45s | %s\n", name, cmd, comment; \
		} \
	' $(ALIAS_FILE)