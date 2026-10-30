#!/usr/bin/env python3
"""
FocusBuddy guardrail hook for Claude Code (PreToolUse).

Blocks, before they happen:
  - writing API keys / private keys into any file
  - writing real secrets into .env files (only .env.example is allowed)
  - destructive or irreversible shell commands (rm -rf, force push, hard reset, sudo, ...)
  - shell commands that would print secret env vars into the transcript

Exit code 2 = block the tool call; the message on stderr is shown to Claude.
Any internal error fails open (exit 0) so a hook bug never blocks normal work.
"""
import json
import os
import re
import sys

SECRET_PATTERNS = [
    (r"gsk_[A-Za-z0-9]{20,}", "Groq API key"),
    (r"sk-(?:ant-|proj-|or-v1-)?[A-Za-z0-9_\-]{20,}", "OpenAI / Anthropic / OpenRouter API key"),
    (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (r"ghp_[A-Za-z0-9]{36}", "GitHub token"),
    (r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----", "private key"),
]

DANGEROUS_COMMANDS = [
    (r"\brm\s+-[a-zA-Z]*(?:[rR][a-zA-Z]*f|f[a-zA-Z]*[rR])\b", "recursive force delete (rm -rf)"),
    (r"\bgit\s+push\b.*(?:--force\b|--force-with-lease\b|\s-f\b)", "force push"),
    (r"\bgit\s+reset\s+--hard\b", "hard reset (discards work)"),
    (r"\bgit\s+clean\s+-[a-zA-Z]*f", "git clean -f (deletes untracked files)"),
    (r"\bsudo\b", "sudo"),
    (r"\bmkfs\b|\bdd\s+if=", "disk formatting / raw disk write"),
    (r"\bchmod\s+-R\s+777\b", "chmod -R 777"),
    (r"(?:curl|wget)\b[^|]*\|\s*(?:sudo\s+)?(?:ba|z)?sh\b", "piping a download into a shell"),
    (r"\besptool(?:\.py)?\b.*\berase_flash\b", "erasing ESP32 flash"),
    (r"(?i:\bDROP\s+TABLE\b|\bDELETE\s+FROM\s+(?:telemetry|events)\b)", "deleting FocusBuddy history"),
]

SECRET_ENV_ECHO = re.compile(r"\$\{?(?:LLM_API_KEY|ODOO_API_KEY|ODOO_PASSWORD)\b|\bprintenv\b|^\s*env\s*$")


def block(reason):
    sys.stderr.write(
        f"FocusBuddy guardrail blocked this action: {reason}.\n"
        "See CLAUDE.md > Hard rules. If this is truly intended, ask the user to run it themselves.\n"
    )
    sys.exit(2)


def written_text(tool_input):
    """Only the text being written. Removing a secret (old_string) must stay allowed."""
    parts = [tool_input.get("content"), tool_input.get("new_string")]
    for e in tool_input.get("edits") or []:
        parts.append(e.get("new_string"))
    return "\n".join(p for p in parts if isinstance(p, str))


def check_write(tool_input):
    path = str(tool_input.get("file_path", ""))
    name = os.path.basename(path)
    if re.fullmatch(r"\.env(\..+)?", name) and name != ".env.example":
        block(f"writing to {name}; secrets belong in the user's shell, put placeholders in .env.example")
    text = written_text(tool_input)
    for pattern, label in SECRET_PATTERNS:
        if re.search(pattern, text):
            block(f"the new content contains what looks like a {label}; use an env var or a placeholder")


def check_bash(tool_input):
    cmd = str(tool_input.get("command", ""))
    for pattern, label in DANGEROUS_COMMANDS:
        if re.search(pattern, cmd):
            block(label)
    if SECRET_ENV_ECHO.search(cmd):
        block("this command could print a secret env var into the transcript")


def main():
    try:
        data = json.load(sys.stdin)
        tool = data.get("tool_name", "")
        tool_input = data.get("tool_input") or {}
    except Exception:
        return 0
    if tool in ("Write", "Edit", "MultiEdit"):
        check_write(tool_input)
    elif tool == "Bash":
        check_bash(tool_input)
    return 0


if __name__ == "__main__":
    sys.exit(main())
