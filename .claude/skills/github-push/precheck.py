#!/usr/bin/env python3
"""
Pre-push safety check for FocusBuddy.

Usage:  python3 .claude/skills/github-push/precheck.py [PROJECT_DIR] [--allow-wifi]

Checks everything that `git add -A && git push` would publish:
  - the git repo root is the project folder (not a parent such as $HOME)
  - warns if a parent folder is also a git repo (easy to push the wrong tree)
  - remote, branch, upstream and unpushed commits
  - forbidden files (.env, databases, private keys, ssh keys)
  - API keys / private keys in files and in unpushed commits (patterns shared with the guardrail hook)
  - real Wi-Fi passwords in firmware (WIFI_PASS); --allow-wifi only after the user confirms it's a throwaway
  - files over GitHub's limits (warn > 50 MB, block > 100 MB)

Exit 0 = safe to commit and push, 1 = blocked (fix the ERROR lines first).
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "hooks"))
from guardrails import SECRET_PATTERNS  # noqa: E402  (single source of truth with the hook)

WIFI_PASS_RE = re.compile(r'WIFI_PASS\s*=\s*"([^"]*)"')
WIFI_PLACEHOLDERS = {"", "focus1234", "your-hotspot-password", "YOUR_WIFI_PASSWORD", "password", "changeme"}
FORBIDDEN = re.compile(r"(^|/)(\.env(\.(?!example$)[^/]+)?|[^/]+\.(db|sqlite3?|pem|key)|id_(rsa|ed25519|ecdsa)[^/]*|\.ssh/.*)$")
WARN_MB, BLOCK_MB = 50, 100

errors, warnings = [], []


def git(*args, cwd):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def scan_text(text, where):
    for lineno, line in enumerate(text.splitlines(), 1):
        for pattern, label in SECRET_PATTERNS:
            if re.search(pattern, line):
                errors.append(f"{where}:{lineno}: looks like a {label} (value hidden)")
        m = WIFI_PASS_RE.search(line)
        if m and m.group(1) not in WIFI_PLACEHOLDERS and "--allow-wifi" not in sys.argv:
            errors.append(f"{where}:{lineno}: real-looking WIFI_PASS (\"<{len(m.group(1))} chars hidden>\") "
                          "- replace with a placeholder, or rerun with --allow-wifi only if the user confirms it's a throwaway")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    project = os.path.realpath(args[0] if args else os.getcwd())
    print(f"Project: {project}")

    # 1. Repo root
    rc, top, err = git("rev-parse", "--show-toplevel", cwd=project)
    if rc != 0:
        errors.append(f"not a git repo yet ({err}); run: git -C '{project}' init")
        return report()
    top = os.path.realpath(top)
    if top != project:
        errors.append(f"git repo root is {top}, not the project. Committing here would publish everything under {top}. "
                      f"Create a repo in the project instead: git -C '{project}' init")
        return report()

    # 2. Parent repos (e.g. an accidental `git init` in $HOME)
    _, origin, _ = git("remote", "get-url", "origin", cwd=project)
    parent = os.path.dirname(project)
    while parent and parent != os.path.dirname(parent):
        if os.path.isdir(os.path.join(parent, ".git")):
            _, p_origin, _ = git("remote", "get-url", "origin", cwd=parent)
            same = " with THE SAME origin remote" if p_origin and p_origin == origin else ""
            warnings.append(f"parent folder {parent} is also a git repo{same}. "
                            f"Always run git as `git -C '{project}' …` so you never push the parent tree")
        parent = os.path.dirname(parent)

    # 3. Remote / branch / upstream
    _, branch, _ = git("branch", "--show-current", cwd=project)
    if not branch:
        errors.append("detached HEAD; check out a branch first")
    print(f"Branch:  {branch or '(detached)'}")
    print(f"Origin:  {origin or '(none)'}")
    if not origin:
        warnings.append("no 'origin' remote; ask the user for the GitHub repo URL")
    rc, upstream, _ = git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", cwd=project)
    upstream = upstream if rc == 0 else ""
    print(f"Upstream: {upstream or '(none - first push will need -u)'}")

    # 4. Files that would be published after `git add -A`
    _, listing, _ = git("ls-files", "--cached", "--others", "--exclude-standard", cwd=project)
    files = [f for f in listing.splitlines() if f and os.path.isfile(os.path.join(project, f))]
    _, status, _ = git("status", "--porcelain", "--untracked-files=all", cwd=project)
    print(f"Files in tree: {len(files)}   Pending changes: {len(status.splitlines()) if status else 0}")
    if status:
        print("\n".join("  " + s for s in status.splitlines()[:40]))

    for f in files:
        path = os.path.join(project, f)
        if FORBIDDEN.search(f):
            errors.append(f"{f}: must not be published (secret/env/database/key file); add it to .gitignore"
                          + (" and `git rm --cached` it" if git("ls-files", "--error-unmatch", f, cwd=project)[0] == 0 else ""))
        mb = os.path.getsize(path) / 1e6
        if mb > BLOCK_MB:
            errors.append(f"{f}: {mb:.0f} MB exceeds GitHub's 100 MB file limit")
        elif mb > WARN_MB:
            warnings.append(f"{f}: {mb:.0f} MB (GitHub warns above 50 MB)")
        try:
            with open(path, "r", encoding="utf-8") as fh:
                scan_text(fh.read(), f)
        except (UnicodeDecodeError, OSError):
            pass  # binary file

    # 5. Secrets inside commits that haven't been pushed yet (removed from files but still in history)
    rng = [f"{upstream}..HEAD"] if upstream else ["HEAD"]
    rc, unpushed, _ = git("log", "--oneline", *rng, cwd=project)
    if rc == 0 and unpushed:
        print(f"Unpushed commits:\n" + "\n".join("  " + c for c in unpushed.splitlines()[:20]))
        _, patch, _ = git("log", "-p", "--format=", *rng, cwd=project)
        added = "\n".join(l[1:] for l in patch.splitlines() if l.startswith("+") and not l.startswith("+++"))
        before = len(errors)
        scan_text(added, "unpushed history")
        if len(errors) > before:
            errors.append("a secret is inside unpushed commits; removing it from the file is not enough. "
                          "Stop and ask the user how to rewrite those local commits")
    return report()


def report():
    print()
    for w in warnings:
        print("WARN  " + w)
    for e in errors:
        print("ERROR " + e)
    if errors:
        print(f"\nBLOCKED: {len(errors)} problem(s). Fix them before committing or pushing.")
        return 1
    print("OK: safe to commit and push.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
