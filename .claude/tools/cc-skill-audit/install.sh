#!/usr/bin/env bash
# cc-skill-audit installer
# Installs CLI to PATH and optionally sets up Claude Code PreToolUse hook
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"

echo "cc-skill-audit installer"
echo "========================"
echo ""

# ─── Check dependencies ─────────────────────────────────────
echo "Checking dependencies..."
for cmd in grep find awk sed python3; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "ERROR: required command '$cmd' not found" >&2
    exit 1
  fi
done
echo "  All dependencies found."
echo ""

# ─── Install CLI ────────────────────────────────────────────
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"
mkdir -p "$INSTALL_DIR"

cp "$REPO_DIR/bin/cc-skill-audit" "$INSTALL_DIR/cc-skill-audit"
chmod +x "$INSTALL_DIR/cc-skill-audit"
echo "CLI installed: $INSTALL_DIR/cc-skill-audit"

# Check PATH
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$INSTALL_DIR"; then
  echo ""
  echo "NOTE: $INSTALL_DIR is not in your PATH."
  echo "Add this to your shell profile:"
  echo "  export PATH=\"$INSTALL_DIR:\$PATH\""
fi
echo ""

# ─── Install Claude Code hook (optional) ────────────────────
if [ ! -d "$CLAUDE_DIR" ]; then
  echo "Claude Code directory not found ($CLAUDE_DIR)."
  echo "Skipping hook installation. You can still use the CLI directly."
  echo ""
  echo "Done!"
  exit 0
fi

echo "Install Claude Code PreToolUse hook? (y/N)"
read -r REPLY
if [[ ! "$REPLY" =~ ^[Yy]$ ]]; then
  echo "Skipping hook installation."
  echo ""
  echo "Done! Run: cc-skill-audit /path/to/skill"
  exit 0
fi

# Copy hook script
SCRIPTS_DIR="$CLAUDE_DIR/scripts"
mkdir -p "$SCRIPTS_DIR"
cp "$REPO_DIR/hook/pre-install-guard.sh" "$SCRIPTS_DIR/pre-install-guard.sh"
chmod +x "$SCRIPTS_DIR/pre-install-guard.sh"

# Hook resolves CLI from PATH at runtime — no path patching needed

# Backup settings.json
SETTINGS="$CLAUDE_DIR/settings.json"
if [ -f "$SETTINGS" ]; then
  cp "$SETTINGS" "${SETTINGS}.bak.$(date +%Y%m%d%H%M%S)"
  echo "  Backed up: ${SETTINGS}.bak.*"
fi

# Merge hook into settings.json
HOOK_CMD="bash $SCRIPTS_DIR/pre-install-guard.sh"
if [ -f "$SETTINGS" ] && grep -q "pre-install-guard" "$SETTINGS" 2>/dev/null; then
  echo "  Hook already present in settings.json — skipping."
else
  # Pass values as sys.argv (prevents injection if env vars contain quotes)
  python3 - "$SETTINGS" "$HOOK_CMD" <<'PYEOF'
import json
import os
import sys

settings_path = sys.argv[1]
hook_cmd = sys.argv[2]
hook_entry = {
    "type": "command",
    "command": hook_cmd,
    "timeout": 3,
}

try:
    with open(settings_path) as f:
        settings = json.load(f)
except FileNotFoundError:
    settings = {}
except json.JSONDecodeError:
    print("  ERROR: settings.json is malformed — refusing to overwrite. Fix it manually.", file=sys.stderr)
    sys.exit(1)

hooks = settings.setdefault("hooks", {})
pre_tool = hooks.setdefault("PreToolUse", [])

# Avoid duplicates
if not any("pre-install-guard" in str(h.get("command", "")) for h in pre_tool):
    pre_tool.append(hook_entry)

# Atomic write via temp file + rename
tmp_path = settings_path + ".tmp"
try:
    with open(tmp_path, "w") as f:
        json.dump(settings, f, indent=2)
    os.replace(tmp_path, settings_path)
    print("  Hook added to settings.json")
except Exception as e:
    try:
        os.unlink(tmp_path)
    except OSError:
        pass
    print(f"  ERROR: failed to write settings.json: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
fi

# Install /audit-skill (optional Claude Code skill)
SKILL_DIR="$CLAUDE_DIR/skills/audit-skill"
if [ -d "$REPO_DIR/extras/claude-code" ] && [ -f "$REPO_DIR/extras/claude-code/SKILL.md" ]; then
  mkdir -p "$SKILL_DIR"
  cp "$REPO_DIR/extras/claude-code/SKILL.md" "$SKILL_DIR/SKILL.md"
  echo "  /audit-skill installed: $SKILL_DIR"
fi

echo ""
echo "Done! Your Claude Code is now protected."
echo ""
echo "Usage:"
echo "  cc-skill-audit /path/to/skill    # scan a skill directory"
echo "  cc-skill-audit /path/to/skill --json  # JSON output"
echo ""
echo "The hook will automatically intercept skill installations."
echo "Set CC_SKILL_AUDIT_RED_ACTION=deny to block RED-rated installs."
