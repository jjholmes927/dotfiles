#split everything out into separate files and sourced them
for file in ~/.profile.d/*
do
  source $file
done
export PATH="/usr/local/opt/openssl@3.0/bin:$PATH"


export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion
export PATH="/opt/homebrew/opt/libpq/bin:$PATH"

# Added by `rbenv init` on Tue 17 Jun 2025 20:50:44 BST
eval "$(rbenv init - --no-rehash bash)"

export PATH="$PATH:$HOME/.local/bin"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"

# mempalace: make python3 -m mempalace work for Claude Code hooks
export PYTHONPATH="/Users/jjholmes/.local/pipx/venvs/mempalace/lib/python3.14/site-packages${PYTHONPATH:+:$PYTHONPATH}"
