---
name: github-push
description: Use when the user asks to push, upload, publish, sync, back up or submit the FocusBuddy code to GitHub, to commit and push changes, to create or connect the GitHub repo, or when a push is rejected — including under a hackathon submission deadline.
---

# Push FocusBuddy to GitHub

**Core rule:** nothing reaches GitHub until `precheck.py` passes and the user has seen exactly what will be published. The repo `Vipulkhanna55/Focusbuddy` is **public**: a pushed secret is a leaked secret, and deleting it later does not unpublish it.

## Environment facts

| Fact | Consequence |
|---|---|
| Project repo `/home/vipul/Desktop/Projects/Focusbuddy`, `origin` = `https://github.com/Vipulkhanna55/Focusbuddy.git` | Push target. Read the branch from `git branch --show-current`, never from a session snapshot |
| **`/home/vipul` is ALSO a git repo with the same `origin`** | Run every git command as `git -C "$P" …`. Never run git from `~` |
| No `gh` CLI | New repo → the user creates it on github.com, then `git -C "$P" remote add origin <url>` |
| git 2.25 | No `git init -b`. Use `git init && git checkout -b main` |
| HTTPS remote | Uses the user's credential helper. `GIT_TERMINAL_PROMPT=0` makes a missing login fail fast instead of hanging |

## Procedure

```bash
P=/home/vipul/Desktop/Projects/Focusbuddy; B=$(git -C "$P" branch --show-current)
python3 "$P/.claude/skills/github-push/precheck.py" "$P"   # 1. must end with "OK"
git -C "$P" status --short                                  # 2. what changed
git -C "$P" fetch origin && git -C "$P" status -sb          # 3. "behind N" → pull --rebase --autostash origin "$B" now
```

4. **Fix every `ERROR`, then rerun precheck.** For a real `WIFI_PASS`, swap in `"your-hotspot-password"`. Tell the user to put the real value back locally before flashing and never commit it. Use `--allow-wifi` only if the user explicitly says the password is a throwaway. SSID and private LAN IPs aren't secrets, so precheck doesn't flag them.
5. **Show what will be published:** the files, the commit message, and `$B → origin/$B`. Leave out unrelated files (notes, scratch) unless the user includes them.
   - If the user said "don't ask" or "just do it", post this as a status line. The commit and push permission prompts are then their checkpoint.
   - Otherwise, ask and wait for their OK.
6. Stage the approved paths (`git -C "$P" add <paths>`; `-A` only if the whole list was approved), then commit.
7. `GIT_TERMINAL_PROMPT=0 git -C "$P" push -u origin "$B"`
8. **Verify:** `git -C "$P" ls-remote origin "$B"` equals `git -C "$P" rev-parse HEAD`. Report the hash and `https://github.com/Vipulkhanna55/Focusbuddy/commit/<hash>`.

## When the push is rejected

| Situation | Do |
|---|---|
| `rejected (fetch first / non-fast-forward)` | `git -C "$P" pull --rebase --autostash origin "$B"` → rerun precheck → push |
| Rebase conflict | Read both sides and combine them by hand. Then `git -C "$P" add <file> && GIT_EDITOR=true git -C "$P" rebase --continue`. If they can't be combined, show both versions and let the user choose. Taking one whole side (`--ours` / `--theirs`) is the user's call |
| Deadline too tight | `git -C "$P" rebase --abort` → `git -C "$P" push -u origin HEAD:submission` → give the user that branch URL |
| `Authentication failed` / `could not read Username` | Stop. The user signs in and reruns the push. Never ask for a token in chat |

## Never

`git push --force`/`-f`, `git reset --hard`, `git clean -f`, `rm -rf` (all blocked by the guardrail hook) · committing `.env`, `*.db` or keys · running git from `/home/vipul`.

## Secret already on GitHub

Precheck only catches what's in the working tree and in unpushed commits. Anything in pushed commits is already public. Tell the user:
1. **Rotate it now.** Change the hotspot password or revoke the key. This is the only real fix.
2. Replace the value with a placeholder and push that.
3. Rewriting history needs a force push, so it is the user's own decision and their own command.

## Red flags

| Thought | Reality |
|---|---|
| "Deadline — skip the check" | Precheck takes about 1 s. A leak is permanent |
| "It's only a Wi-Fi password" | Anyone near the hotspot can join it, and the repo is public |
| "I removed the key from the file" | It's still in unpushed commits; precheck scans those too |
| "Keep my side of the conflict, it's faster" | That silently deletes someone's work |
| "User said push, so they approved" | They approved pushing, not this file list. Show it (step 5) |
