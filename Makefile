PREFIX            := $(HOME)
SHELL_CONFIG_DIR  := $(PREFIX)/.config/shell
ALIAS_FILE        := aliases
TARGET_ALIAS_FILE := $(SHELL_CONFIG_DIR)/aliases

BASHRC := $(PREFIX)/.bashrc
ZSHRC  := $(PREFIX)/.zshrc

.PHONY: install refresh update sort

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