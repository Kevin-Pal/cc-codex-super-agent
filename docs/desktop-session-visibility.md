# Desktop visibility is separate from Worker lifecycle

## 0.3.0 follow-up

Two legacy formal Workers were repaired at idle through the native same-ID reload path. Both retained their original IDs and returned the central project cwd; the access-side Desktop project/thread API then associated both with the same attached parent Project. This is a current client-API observation, not a screenshot or a promise across every Desktop version. The old research checkout/artifacts were retained. New owned formal Workers cannot be created at a worktree/subdirectory instead of the Router entry.

> 0.3.0: formal Workers now stay at their Router project entry; only temps may request managed worktree isolation. Shared knowledge, explicit external control, same-ID legacy repair and checked cleanup are specified in [project paths](project-paths.md). Earlier observations/proposals below retain their historical scope; the new contract supersedes conflicting cwd/worktree suggestions.

A formal Worker finishing a task should keep its native thread and framework registration. It is not automatically released, archived or deleted. An empty Desktop Project is not evidence that its Workers were removed.

## Four separate states

| Layer | What it tells you | What it does not imply |
| --- | --- | --- |
| Framework registration | Worker kind, owning Router, workstream and control mode | Membership in a Desktop Project |
| Task state | Running, ready, accepted, blocked or failed | End of a persistent Worker |
| Native thread | Persisted versus ephemeral, loaded versus unloaded, archived versus active history | Current placement in a Desktop list |
| Desktop presentation | Project grouping, Recents, filters and the connected host | The authoritative Worker roster or proof of deletion |

`ai-work control ... --pin` prioritizes the framework roster; it does not pin a chat in Desktop. `released` relinquishes framework management and retains the record; it does not archive or delete the native chat. Desktop archive is a separate human action and is not a reliable stop-dispatch signal in this release. See [session lifecycle](session-lifecycle.md).

## Paths and history filters

Use the same execution host, user and native session storage when locating a Worker. The Project label is not the Worker's identity. A project entry directory is useful for discovery, but adding its parent folder does not guarantee recursive inclusion of all subdirectory or sibling-worktree threads.

The [official App Server protocol](https://learn.chatgpt.com/docs/app-server#list-threads-with-pagination--filters) documents an exact-match `cwd` filter, not a recursive directory search. Its default thread sources are interactive `cli` and `vscode`; older `exec` or subagent records may require explicit source selection even when their transcripts still exist. These protocol filters help diagnose missing history; they do not establish the private implementation of every Desktop view.

Framework temp Workers use native `ephemeral: true`, retain task results/reviews in the coordinator, and are released/unsubscribed after completion. They are intended to stay out of durable normal history. A transient live entry alone does not identify a temp Worker. A standard `Worker_...` title and previous human conversation are not grounds to assume normal temp cleanup: verify the native ID and registration.

Unloading or unsubscribing a persisted thread is also different from archiving or deleting it. The [official protocol](https://learn.chatgpt.com/docs/app-server#unsubscribe-from-a-loaded-thread) describes these as separate operations. Do not infer lost history from a `notLoaded` status.

## Observed grouping limitation

On 2026-11-02, with framework 0.2.3, native Codex 0.166.0 and a Mac Desktop remote access client, two formal Workers remained registered, persisted, unarchived and idle after multiple accepted tasks. One used a nested repository directory; the other used a sibling linked worktree. Both were returned by the Desktop-specific history interface with no Project association, while the user reported an empty parent Project and found them in Recents.

An earlier read-only check had associated the same linked-worktree sample with the parent Project. That earlier observation is a point-in-time result, not a stable grouping guarantee. The follow-up did not establish why the association changed; the independent GUI build and a visual recording were not collected. A separately reported entry that disappeared after completion could not be identified by native ID/title and remains unclassified. It is not a verified temp-cleanup or formal-thread-deletion case. Instance paths, IDs and transcripts stay in private operations records.

## Finding a Worker without disturbing it

1. Confirm the remote host/user/session store, and find the exact registered native ID through the owning Router's roster. `list --all` includes that Router's released registrations; it does not enumerate every native chat.
2. Check Desktop Recents/history and archived history separately. Compare the ID, title, current `cwd` and Project association. Investigate old `exec` sources separately when relevant.
3. Use a read-only native summary to distinguish an unloaded, unarchived persisted thread from a temporary thread. Check task results and actual artifacts before considering any retry.
4. Reuse the original thread. Do not create a replacement, automatically adopt another Router's chat, or edit Codex's internal database to fix grouping. Human intervention still requires normal synchronization and control coordination.

For future formal Workers, prefer a stable project entry when compatible with the task's execution and isolation needs; describe other target paths explicitly. Do not relocate an existing active thread merely to tidy the sidebar. Explicit Project association and separating `project_root` from `execution_cwd` need supported interfaces and further tests; they are not implemented by this documentation update. See [parallel Worker design](history/parallel-workers-design.md).
