set dotenv-load := true

# Bare `just` lists every recipe (first recipe = default — keep this one on top).
default:
    @just --list

# fusion-harness — 2-5 configured agents, AND not OR.
WORKHORSE_ARCHITECT := "anthropic/claude-sonnet-5"
WORKHORSE_BUILDER := "openai/gpt-5.6-terra"
SOTA_ARCHITECT := "anthropic/claude-fable-5"
SOTA_BUILDER := "openai/gpt-5.6-sol"

# Cheap legacy two-slot pair. Raw chat is the builder.
fh-workhorse *ARGS:
    pi -e extensions/fusion-harness/fusion-harness.ts \
        --model {{WORKHORSE_BUILDER}} \
        --architect {{WORKHORSE_ARCHITECT}} --builder {{WORKHORSE_BUILDER}} \
        --architect-thinking medium --builder-thinking medium \
        {{ARGS}}

# Frontier legacy two-slot pair.
fh-sota *ARGS:
    pi -e extensions/fusion-harness/fusion-harness.ts \
        --model {{SOTA_BUILDER}} \
        --architect {{SOTA_ARCHITECT}} --builder {{SOTA_BUILDER}} \
        --architect-thinking medium --builder-thinking medium \
        {{ARGS}}

# Explicit 2-5 slot YAML stack. The extension selects configured Main as host.
fh-stack CONFIG *ARGS:
    pi -e extensions/fusion-harness/fusion-harness.ts \
        --fh-config {{CONFIG}} {{ARGS}}

# THE fusion stack: rune=Fable 5 architect · flux=Gemini 3.7 Flash Main · drift=DeepSeek V4 Pro
fusion *ARGS:
    just fh-stack .pi/fusion-harness/model-stack-fusion.yaml {{ARGS}}

# 5-slot fusion stack: fusion trio + fire=Kimi K3 + hawk=DeepSeek V4 Flash (both Fireworks)
fusion5 *ARGS:
    just fh-stack .pi/fusion-harness/model-stack-fusion-5.yaml {{ARGS}}

# self-compact agent brief shared by Claude Code, Codex CLI, and Pi.
SELF_COMPACT_BRIEF := "self-compact/SELF_COMPACT_AGENT_BRIEF.md"

# Print the shared self-compact contract.
self-compact:
    @cat {{SELF_COMPACT_BRIEF}}

# Print the Claude Code version of the self-compact brief.
self-compact-claude:
    @printf 'Target agent: Claude Code\n\n'
    @cat {{SELF_COMPACT_BRIEF}}

# Print the Codex CLI version of the self-compact brief.
self-compact-codex:
    @printf 'Target agent: Codex CLI\n\n'
    @cat {{SELF_COMPACT_BRIEF}}

# Print the Pi version of the self-compact brief.
self-compact-pi:
    @printf 'Target agent: Pi\n\n'
    @cat {{SELF_COMPACT_BRIEF}}

# Copy an agent-targeted self-compact prompt to the macOS clipboard.
self-compact-copy AGENT="pi":
    @printf 'Target agent: {{AGENT}}\n\n' > /tmp/self-compact-agent-brief.md
    @cat {{SELF_COMPACT_BRIEF}} >> /tmp/self-compact-agent-brief.md
    @pbcopy < /tmp/self-compact-agent-brief.md
    @printf 'Copied self-compact brief for %s to clipboard.\n' '{{AGENT}}'

# Raw compound prompt written by Evan for self-compact implementation runs.
compound := "self-compact/prompt.compound.md"

# Start Claude Code with the compound prompt appended to Claude's system prompt.
compound-claude:
    claude --append-system-prompt "$(cat {{compound}})"

# Start Codex CLI with the compound prompt as the initial prompt. Codex has no system-prompt flag in this CLI.
compound-codex:
    codex "$(cat {{compound}})"

# Start Pi with the compound prompt appended to Pi's system prompt.
compound-pi:
    pi --append-system-prompt "$(cat {{compound}})"

# Start Hermes with the compound prompt as the first interactive turn. Hermes has no system-prompt flag here.
compound-hermes:
    hermes chat --query-file {{compound}}

# Start the default global fusion stack with the compound prompt appended to Pi's system prompt.
compound-fusion:
    fusion pi --append-system-prompt "$(cat {{compound}})"

# Alias for the default global fusion stack with the compound prompt.
compound-fusion-pi:
    fusion pi --append-system-prompt "$(cat {{compound}})"

# Start the local fusion stack with the compound prompt.
compound-fusion-local:
    fusion local --append-system-prompt "$(cat {{compound}})"

# Start the repo five-slot fusion stack with the compound prompt.
compound-fusion5:
    fusion 5 --append-system-prompt "$(cat {{compound}})"
