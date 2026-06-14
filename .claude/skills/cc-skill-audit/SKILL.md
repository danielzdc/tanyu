---
name: cc-skill-audit
description: Security scanner for Claude Code third-party skills. Use BEFORE installing any skill from untrusted sources. Detects telemetry, data exfiltration, obfuscated code, binary blobs, hardcoded API keys, and suspicious patterns. Trigger: user wants to install a skill, audit a skill, check a skill for security, review skill safety.
---

# cc-skill-audit — Skill Security Scanner

Security scanner & PreToolUse firewall for Claude Code third-party skills.
Detects undisclosed telemetry, outbound data exfiltration, obfuscated code,
binary blobs, and suspicious patterns **before** you install a third-party skill.

## When to Use

Use this skill when:
- User wants to install a skill from an untrusted source
- User asks "is this skill safe?"
- User wants to audit/review a skill before installing
- User says "check this skill for me"

## How to Run

```bash
bash /d/项目/.claude/tools/cc-skill-audit/cc-skill-audit <path-to-skill-directory>
```

For JSON output:
```bash
bash /d/项目/.claude/tools/cc-skill-audit/cc-skill-audit <path-to-skill-directory> --json
```

For quick exit-code-only check (0=GREEN, 1=YELLOW, 2=RED):
```bash
bash /d/项目/.claude/tools/cc-skill-audit/cc-skill-audit <path-to-skill-directory> --fast
```

## What It Scans

| Category | Patterns |
|----------|----------|
| Telemetry | telemetry, analytics, supabase, firebase, segment, sentry, beacon |
| Network | fetch(), curl, wget, axios, XMLHttpRequest, sendBeacon, WebSocket |
| API keys | Hardcoded AWS, GitHub, OpenAI, Supabase, Slack tokens |
| Sensitive reads | .git/config, .ssh/*, .gnupg/*, .env, .npmrc |
| Dotfile writes | Creating hidden state directories outside the skill folder |
| Data fields | repo, branch, session, hostname, conversation, etc. |
| Consent | opt-in/disable_telemetry flags |
| Obfuscation | Base64, string concatenation, hex/unicode escapes, dynamic require/import |
| Binary blobs | ELF, Mach-O, PE32, WebAssembly detection |
| Dependencies | package.json postinstall scripts, requirements.txt |

## Risk Levels

| Level | Meaning |
|-------|---------|
| GREEN | No suspicious patterns — safe to install |
| YELLOW | Has telemetry (opt-in), or network calls — review needed |
| RED | Hardcoded keys, sensitive reads, undisclosed telemetry, obfuscation — BLOCK |

## After Scanning

Present findings clearly:
1. Overall risk level (GREEN/YELLOW/RED)
2. Severity score (0-100)
3. List each finding with file path and line
4. Recommendation: install / review first / do not install
