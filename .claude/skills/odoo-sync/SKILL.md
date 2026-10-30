---
name: odoo-sync
description: (Planned integration) Use when the user asks to push FocusBuddy focus sessions or daily reports into Odoo (Timesheets / Project) through the Odoo MCP server in .mcp.json. Read-only by default; every write needs explicit confirmation.
---

# Odoo sync via MCP (planned)

> **Status: roadmap.** `.mcp.json` holds a reference config for the community `mcp-server-odoo` server. It is **not connected** in the hackathon build. If the `odoo` MCP tools aren't available in this session, say so and stop. Never pretend a sync happened.

Design: `docs/ODOO_INTEGRATION.md`.

## Mapping

| FocusBuddy | Odoo model | Field |
|---|---|---|
| Completed focus session(s) for a day | `account.analytic.line` (timesheet line) | `unit_amount` = hours, `date`, `name` = "FocusBuddy: N sessions, M min focus" |
| Project being studied | `project.project` / `project.task` | `project_id`, `task_id` (user picks) |
| The student / employee | `hr.employee` | `employee_id` |
| Daily AI report | timesheet `name` or a note on the task | plain text, ≤ 500 chars |

## Data source (read from FocusBuddy, never from raw DB edits)

```bash
curl -s -XPOST http://<phone-ip>:5000/api/summary -H 'Content-Type: application/json' -d '{"speak":false}'
```
Use the returned `facts` (focus minutes, sessions). Don't send distance/light series or the activity log to Odoo — data minimisation.

## Procedure

1. **Read first.** Use the MCP search tools to find the user's employee, project and task. Show the matches.
2. **Draft.** Build the timesheet line and show it to the user as a table: date, project, task, hours, description.
3. **Confirm.** Write only after the user explicitly says yes. One record per confirmation.
4. **Write.** Create the `account.analytic.line`. Report the new record id.
5. **Never** update or delete existing Odoo records, touch accounting/invoicing/payroll models, or change user access rights.

## Guardrails

- Credentials come only from env vars (`ODOO_URL`, `ODOO_DB`, `ODOO_API_KEY`). Never ask for them in chat, never write them to files (the guardrail hook blocks key-shaped strings).
- Use a dedicated Odoo API user with access limited to Project + Timesheets.
- Prefer the server's read-only mode for exploration; only enable writes for the sync step.
- Round hours to 0.25 h; never log more than the focus minutes FocusBuddy actually measured.
