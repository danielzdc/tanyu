#!/usr/bin/env bash
# PreToolUse hook: intercept skill installations into ~/.claude/skills/
#
# Triggers on: ln, cp, mv, or setup/install scripts targeting ~/.claude/skills/
# Calls cc-skill-audit CLI in --fast mode for quick risk assessment.
#
# Risk decisions:
#   GREEN  -> allow (no suspicious patterns)
#   YELLOW -> ask   (needs manual review)
#   RED    -> ask   (suspicious — review strongly recommended)
#
# Configure RED behavior via CC_SKILL_AUDIT_RED_ACTION:
#   "ask"  = prompt user (default, recommended for observation period)
#   "deny" = block installation

set -uo pipefail

# ─── Locate CLI ──────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLI="${SCRIPT_DIR}/../bin/cc-skill-audit"

if [ ! -x "$CLI" ]; then
  # Fallback: check PATH
  CLI="$(command -v cc-skill-audit 2>/dev/null || true)"
  if [ -z "$CLI" ]; then
    exit 0  # CLI not found — fail open with no opinion
  fi
fi

# ─── Read hook input ─────────────────────────────────────────
INPUT=$(cat)

# Quick check: is this a Bash tool call?
if ! echo "$INPUT" | grep -q '"tool_name"'; then
  exit 0
fi

# Parse with python3 (available on macOS + most Linux, no jq dependency)
PARSED=$(python3 -c "
import json, sys
data = json.load(sys.stdin)
tool = data.get('tool_name', '')
cmd = data.get('tool_input', {}).get('command', '')
print(f'{tool}\t{cmd}')
" <<< "$INPUT" 2>/dev/null || true)

TOOL_NAME="${PARSED%%	*}"
COMMAND="${PARSED#*	}"

[ "$TOOL_NAME" != "Bash" ] && exit 0
[ -z "$COMMAND" ] && exit 0

# ─── Check if command targets ~/.claude/skills/ ──────────────
HOME_SKILLS="$HOME/.claude/skills"

# Normalize common path patterns in command string
NORMALIZED_CMD="$COMMAND"
NORMALIZED_CMD="${NORMALIZED_CMD//\~/$HOME}"
NORMALIZED_CMD="${NORMALIZED_CMD//\$HOME/$HOME}"
NORMALIZED_CMD="${NORMALIZED_CMD//\$\{HOME\}/$HOME}"

# Check for skill directory target OR installer scripts
TARGETS_SKILLS=false
IS_INSTALLER=false

if echo "$NORMALIZED_CMD" | grep -q "$HOME_SKILLS"; then
  TARGETS_SKILLS=true
fi

# Also catch setup/install scripts that might create skill symlinks
for keyword in "setup" "install"; do
  if echo "$COMMAND" | grep -qiE "(^|[/[:space:]])$keyword([[:space:]]|\.sh|$)"; then
    IS_INSTALLER=true
    break
  fi
done

# Exit early if not relevant
if [ "$TARGETS_SKILLS" = false ] && [ "$IS_INSTALLER" = false ]; then
  exit 0
fi

# ─── Resolve source directory ────────────────────────────────
# Try to find the source skill directory from the command
SOURCE_DIR=""

# For ln/cp/mv: first non-flag argument is typically the source
ARGS=()
while IFS= read -r word; do
  ARGS+=("$word")
done < <(python3 -c "
import shlex, sys
try:
    tokens = shlex.split(sys.argv[1])
    for t in tokens:
        print(t)
except:
    pass
" "$COMMAND" 2>/dev/null)

for arg in "${ARGS[@]}"; do
  # Skip flags, operators, and command names
  case "$arg" in
    -*|"&&"|"||"|";"|"|"|ln|cp|mv|bash|sh|zsh|sudo|env) continue ;;
  esac

  # Resolve path
  resolved="$arg"
  resolved="${resolved/#\~/$HOME}"
  resolved="${resolved//\$HOME/$HOME}"
  resolved="${resolved//\$\{HOME\}/$HOME}"

  if [ "${resolved#/}" = "$resolved" ]; then
    cwd=$(echo "$INPUT" | python3 -c "import json,sys; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null || pwd)
    resolved="$cwd/$resolved"
  fi

  # First existing directory that's NOT ~/.claude/skills is likely the source
  if [ -d "$resolved" ] && [ "$resolved" != "$HOME_SKILLS" ] && [[ "$resolved" != "$HOME_SKILLS"/* ]]; then
    SOURCE_DIR="$resolved"
    break
  fi

  # If it's a file, use its parent
  if [ -f "$resolved" ]; then
    parent="$(dirname "$resolved")"
    if [ "$parent" != "$HOME_SKILLS" ] && [[ "$parent" != "$HOME_SKILLS"/* ]]; then
      SOURCE_DIR="$parent"
      break
    fi
  fi
done

# ─── Run scan ────────────────────────────────────────────────
emit_decision() {
  local decision="$1"
  local reason="$2"

  # Pass values as sys.argv, never interpolate into the -c string
  # (prevents Python injection via attacker-controlled skill names)
  python3 - "$decision" "$reason" <<'PYEOF' 2>/dev/null
import json
import sys

decision = sys.argv[1]
reason = sys.argv[2]

print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    },
    "systemMessage": reason,
    "suppressOutput": True,
}))
PYEOF
}

if [ -z "$SOURCE_DIR" ]; then
  emit_decision "ask" "SKILL AUDIT [YELLOW] could not resolve source directory — review before install"
  exit 0
fi

# Run CLI in fast mode (with timeout fallback for macOS)
# Note: timeout(1) returns 124 when it kills the child; perl's alarm returns 142 (128+SIGALRM)
if command -v timeout >/dev/null 2>&1; then
  timeout 3 "$CLI" "$SOURCE_DIR" --fast 2>/dev/null
  EXIT_CODE=$?
elif command -v perl >/dev/null 2>&1; then
  perl -e 'alarm 3; exec @ARGV' "$CLI" "$SOURCE_DIR" --fast 2>/dev/null
  EXIT_CODE=$?
else
  "$CLI" "$SOURCE_DIR" --fast 2>/dev/null
  EXIT_CODE=$?
fi

# Distinguish timeout (124/142) from genuine scan error for the user-facing message
if [ "$EXIT_CODE" -eq 124 ] || [ "$EXIT_CODE" -eq 142 ]; then
  TIMED_OUT=1
else
  TIMED_OUT=0
fi

RED_ACTION="${CC_SKILL_AUDIT_RED_ACTION:-ask}"

case $EXIT_CODE in
  0)  # GREEN
    SKILL_NAME="$(basename "$SOURCE_DIR")"
    emit_decision "allow" "SKILL AUDIT [GREEN] $SKILL_NAME — no suspicious patterns"
    ;;
  1)  # YELLOW
    SKILL_NAME="$(basename "$SOURCE_DIR")"
    emit_decision "ask" "SKILL AUDIT [YELLOW] $SKILL_NAME — review recommended. Run: cc-skill-audit $SOURCE_DIR"
    ;;
  2)  # RED
    SKILL_NAME="$(basename "$SOURCE_DIR")"
    emit_decision "$RED_ACTION" "SKILL AUDIT [RED] $SKILL_NAME — suspicious patterns detected! Run: cc-skill-audit $SOURCE_DIR"
    ;;
  *)  # Error or timeout
    if [ "$TIMED_OUT" = "1" ]; then
      emit_decision "ask" "SKILL AUDIT [YELLOW] scan timed out (>3s) — large or slow skill, review manually before install"
    else
      emit_decision "ask" "SKILL AUDIT [YELLOW] scan error (exit $EXIT_CODE) — review before install"
    fi
    ;;
esac
