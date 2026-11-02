---
name: claude-codex-router
description: Direct native Codex Workers from Claude Code, continue a workstream, or review a returned task.
---

Use Claude for intent, planning, constraints, personal review and final refinement. Delegate routine execution by default; personally perform explicitly Claude-assigned design/refinement/cross-checks. A small reversible action may use the direct path.

- New direction: `ai-work open --stream export --direction 导出链路`. The coordinator uses your bound project entry when cwd is omitted, including pre-upgrade sessions without `CCW_PROJECT_ROOT`. It reuses your registered Worker. Do not select a task subdirectory as its cwd. Default tier is hard; easy fits simple batches, xhard fits difficult bottlenecks.
- Find/reuse: `ai-work list --query DIRECTION` searches only your registered persistent sessions. Accepted formal Workers remain idle and reusable; `released` ends management, not a task. Pin a user-designated main Worker with `ai-work control WORKER_ID --pin`; pinning never changes manual/paused control. Names/stream/cwd help discovery; use the exact returned ID.
- One-off: add `--kind temp --tier easy`, omit `--stream`. Temporary results remain auditable; the native chat is ephemeral. Choose a persistent Worker for multi-round iteration.
- Isolation: only a temp may add `--isolation worktree`; select `--repo` for an authorized nested repository and an explicit committed `--base` when the source is dirty. Shared rules remain at the project entry. `review` cleans an accepted, unchanged, idle checkout automatically; changed/unintegrated/busy environments are retained. Use `ai-work workspace` to find them; after integrating/preserving artifacts use `ai-work workspace RESOURCE_ID --cleanup`. Never delete unknown or dirty trees.
- External collaboration: only inspect a user-named session with `ai-work inspect THREAD_ID`. This preserves its owner/path and starts no turn. `adopt` is an explicit control takeover, not ordinary collaboration; coordinate its current owner and keep its existing project rules. Do not create a new Router/team at a child directory; the user starts intentional subprojects there.
- Continue: `ai-work sync WORKER_ID --router "$CCW_ROUTER_ID"`. Read external input and changed project files. Send only the meaningful delta using the returned sync token: `ai-work send WORKER_ID --router "$CCW_ROUTER_ID" --sync-token TOKEN --file /absolute/task.txt --authorization "current approved task"`.
- Return: `ai-work result TASK_ID --router "$CCW_ROUTER_ID"` or `ai-work inbox --router "$CCW_ROUTER_ID"`. Inspect artifacts and material claims, then `ai-work review TASK_ID --router "$CCW_ROUTER_ID" --verdict accept --note "evidence inspected"`. Retrieval or READY is not acceptance.

`--router` may be omitted: it defaults to `CCW_ROUTER_ID`, then `CLAUDE_CODE_SESSION_ID`. Output is JSON.

Formal Workers remain at the Router's project entry; split file/output responsibilities, queue conflicting writes, or send a separable task to an isolated temp. Current same-tree writes remain serialized; distinct filenames are not an automatic lock exemption. Git index/branch writes and shared-state integration need a single executor. To correct a legacy path, inspect first, wait for idle, then use `ai-work repair WORKER_ID --reason TEXT --reload`; it preserves the thread ID but may briefly archive/unarchive it to reload native context. Never repair manual/paused or active work. See [path, ownership and cleanup](references/project-paths.md).

- Waiting: after `send`, end the turn instead of sleeping or polling. The asyncRewake hooks wake an idle Router with "Codex results need Router review"; then read, inspect and review.
- Sandbox: the instance may exempt standalone `ai-work` subcommands from Claude's Bash sandbox. Run each call alone (no pipes, `&&` or command substitution) so the exemption applies; mixed commands stay sandboxed and get `Operation not permitted`. Do not loosen unrelated sandbox rules.
- Claude-assigned substantive work (or Codex unavailable): `ai-work takeover --scope PATH --reason TEXT` grants a bounded direct-write window for the user's actual authorized scope. An explicit assignment needs no repeated permission or quota failure. Read-only cross-checks need no write window. Record changes/evidence, then `--release --note`; refresh Worker sync before further dispatch. See [Claude direct work](references/claude-direct-work.md).

Use exact returned IDs, never guess the newest session. The native session and shared project files carry continuity; do not paste all history. Direct human changes take precedence over stale packages. Pause/manual control persists until explicitly released. Do not create extra Claude sessions for execution.

Load only the relevant guide:

- Creation, continuation, naming, personal/external session takeover: [session protocol](references/worker-sessions.md).
- Concrete goals, assumptions, acceptance and repair feedback: [prompts](references/router-prompts.md).
- Knowledge authority and refreshing long-running sessions: [shared memory](references/project-memory.md).
- CLI commands, wakeup, cancellation and recovery: [operations](references/runtime-operations.md).

If the integration is unavailable, report its actual error and repair the calling/environment issue. Do not silently revert to one-shot exec, duplicate a Worker or ask the user to fetch results for you.
