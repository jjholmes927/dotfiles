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

. "$HOME/.local/bin/env"

# Added by Antigravity
export PATH="/Users/beamtempmacbookpro/.antigravity/antigravity/bin:$PATH"

# bun
export BUN_INSTALL="$HOME/.bun"
export PATH="$BUN_INSTALL/bin:$PATH"
