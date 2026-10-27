# Sourced from ~/.bashrc on the Lenovo.
# Two Claude accounts, one config folder each. API keys and tokens are cleared so one
# from a sourced .env never replaces the subscription login.
claude-a() { env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN CLAUDE_CONFIG_DIR="$HOME/.claude-a" claude "$@"; }
claude-b() { env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN CLAUDE_CONFIG_DIR="$HOME/.claude-b" claude "$@"; }
