# Claude Subscription Usage

Use the Claude Pro/Max subscription's **included limits** instead of extra usage (per-token billing).

## Background

Pi's built-in Anthropic OAuth routes through "extra usage" — billed per token, not against your plan's included limits. The `pi-claude-cli` package fixes this by routing LLM calls through the official Claude Code CLI subprocess, which uses your subscription's included usage.

## Setup (already done)

1. `npm:pi-claude-cli` is added to `.pi/settings.json` packages
2. Claude Code CLI is installed and authenticated (`claude` on PATH)
3. Active Claude Pro or Max subscription

## How to Switch

### Use subscription (no extra billing)
Switch to the `pi-claude-cli` provider via `/model` in the interactive UI. All Claude models appear under the **pi-claude-cli** provider. Select one (e.g., `claude-sonnet-4` or `claude-opus-4`).

Or start pi with:
```bash
autobot --provider pi-claude-cli --model claude-sonnet-4
```

### Use API/extra usage (default)
Switch back to the built-in `anthropic` provider via `/model`.

## Notes

- The `pi-claude-cli` provider spawns `claude -p` as a subprocess per request
- It uses `--resume` on follow-up turns to avoid replaying full history
- Custom pi tools are exposed to Claude via a schema-only MCP server
- Thinking/reasoning works normally with configurable effort levels
- Session state is maintained per-conversation via the CLI's session mechanism
- If you hit your plan's rate limit, you'll be throttled (not billed extra)

## When to Use

**Always prefer this** unless you specifically need:
- API-level rate limits (higher throughput)
- A model not available via Claude Code CLI
- Direct Anthropic API features not supported by the CLI bridge
