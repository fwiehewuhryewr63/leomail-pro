---
description: Lightweight mode - minimize RAM usage on weak hardware
---

# Lightweight Working Mode

## Rules to minimize laptop RAM usage:

1. **NO browser_subagent** — never launch browser. Use `Invoke-WebRequest` or `Invoke-RestMethod` for testing
2. **NO parallel tool calls** — always sequential, one tool at a time
3. **Small file reads** — max 100 lines per view, never full files unless under 50 lines
4. **Minimal grep** — targeted searches, never broad scans
5. **One edit at a time** — don't batch 20+ replacements in one call
6. **Short responses** — no walls of text
7. **Test via API** — `Invoke-WebRequest` instead of opening browsers
8. **Push in batches** — accumulate changes, one git push per session
9. **No task_boundary spam** — only when switching major phases
10. **Wait for user** — don't chain 10 commands automatically, pause after key steps

// turbo-all
