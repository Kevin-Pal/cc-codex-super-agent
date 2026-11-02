# Project paths, ownership and temporary execution

Implemented in 0.3.0. A project entry P is the directory the person intentionally uses to start a Router. It is canonicalized, not automatically promoted to a Git root. A deliberate subproject gets its own Router when the person starts one there.

## Three Router relationships, two human-visible session types

| Relationship | Ownership and path | Human visibility | Conflict and lifetime |
| --- | --- | --- | --- |
| Router-created formal Worker | This Router; native cwd must equal P | Persistent formal chat, intended to be discoverable through the attached project | Reuse the exact native ID; split file/output responsibilities; conflicting writes queue; retain after acceptance |
| Router-created temp | This Router/P; cwd=P or an explicitly managed task worktree | Ephemeral; not a normal durable chat asset | Optional checkout isolation, bounded task, retained result/review; clean only after acceptance and artifact integration/preservation |
| User-named existing session | Its person or existing Router and original path | Personal chat or another formal Worker | Inspect without changing ownership; explicit takeover uses adopt after control coordination; never create an implicit foreign team |

These are workflow relationships, not activation of Claude's native Teams/subagents. Codex remains the execution harness. A human-created session is not automatically a managed Worker. A shared history view does not remove active-turn conflicts or transfer control.

## Deterministic entry and knowledge checks

SessionStart/UserPromptSubmit register the launch entry; hook exports include `CCW_PROJECT_ROOT`. Later cd, worker creation and adoption do not move a bound Router. The coordinator rejects creating a formal Worker at another cwd, rejects formal worktree isolation, and checks native cwd again before sending/dispatching. These checks apply even when an advisory hook was missed.

An unregistered Router cannot first bind itself through open/adopt: establish its launch project through the hook or explicit `ai-work router --cwd PROJECT`. Once bound, open without --cwd uses that binding rather than the caller's current shell directory. The roster/hook marks legacy formal sessions that need path repair.

`sync` hashes central project facts at P. Isolated temps additionally bind their execution HEAD; the work package names both P and execution cwd. All participants read the existing shared AGENTS.md or, when absent, existing CLAUDE.md and authoritative status. Applicable target-local rules still matter. Worktrees do not provide live synchronization of memory files. Changed central facts invalidate queued work. Unmanaged human/native activity is still coordinated by actual input and scope, not an OS sandbox.

Formal Workers keep their native entry at P even when tools operate on explicitly authorized task targets. They must not write into another temp's reserved execution directory. Native project association/Recents remain client-dependent: attach the same host/user/session store/path and verify actual access. Fixed cwd is our contract, not a guarantee against every Desktop display defect.

## Temp worktree operations

```sh
ai-work open --kind temp --direction review --isolation worktree
# A deliberately selected nested repository; a dirty source needs a committed base:
ai-work open --kind temp --direction change --isolation worktree --repo PATH --base REV
ai-work workspace
ai-work workspace RESOURCE_ID --cleanup
# A confirmed stopped/cancelled or unused temp; still refuses dirty/unintegrated work:
ai-work workspace RESOURCE_ID --discard --reason TEXT
# Only after both its directory and Git worktree registration are already gone:
ai-work workspace RESOURCE_ID --forget --reason TEXT
```

The project-local namespace is `.claude/cc-codex-super-agent/`: `worktrees/<repo-key>/<resource-id>/` contains disposable checkouts; `receipts/<resource-id>.json` records provenance outside the checkout. A local Git exclude covers this namespace without editing tracked .gitignore. Nothing copies credentials, provider configuration, ignored environments or uncommitted source changes. Dirty sources require an explicit committed base; preparation failures retain a resource record rather than replaying unknown work.

Only registered, identity-verified managed checkouts may bypass the ordinary parent/child writer conflict with the formal main-project writer. Ordinary subdirectories and whole-directory Router takeover retain conservative conflict handling. Two formal writers in the same tree serialize; filename-specific leases are not planned (disjoint files do not prove semantic compatibility). Formal Workers divide long-term responsibilities but all managed same-tree writes queue; parallel or conflict-prone work goes to an isolated temp. Separate checkouts do not isolate Git metadata, databases, ports, GPUs or arbitrary broad-permission Bash. Git index/branch writes and shared-state integration remain a single-executor responsibility.

`review --verdict accept` tries cleanup only for an accepted temp workspace. If native context processes are still in their unload grace period, the idle coordinator retries one accepted resource at most every 30 seconds; it never relaxes dirty/integration/job checks and makes no model calls for housekeeping. It refuses tracked, untracked or ignored changes, unintegrated commits, changed repository/branch/path identity, manual/paused control, active native work, native background terminals, or visible same-user processes/open files referencing the tree. When verification is unavailable, retain the tree. Results/reviews stay in the private coordinator database, receipts stay outside the tree, and the branch remains a recovery pointer. No force removal, global pruning, chat deletion or automatic cleanup of arbitrary existing trees is performed.

A native-start acknowledgment loss is retained as STARTING/UNCERTAIN with its resource ID; it is not automatically removed or replayed. Registration of a native Worker, its project authority and resource association is transactional. An unused temp that has already unloaded without positive background evidence stays retained for manual inspection; do not infer it stopped from a missing context. Explicit discard never overrides dirty/unintegrated/busy checks. Forget only changes records when the old path and Git registration are absent (or the source repository itself has moved), keeps the previous record in its audit event, and deletes no relocated data.

Changed workspaces normally remain: inspect artifacts, preserve needed outputs outside the checkout, have the designated executor integrate commits and run combined checks, then request cleanup. Timeout/disconnect/unknown task outcomes do not establish completion or authorize retry. Ephemeral reconnection limitations still apply. Native task-job checks and visible OS process checks are local evidence, not proof that every external service stopped. Unrelated permission-protected processes are not inspected.

## Existing sessions and external collaboration

```sh
ai-work inspect THREAD_ID
# Explicit transfer of control, only when requested:
ai-work adopt THREAD_ID --from-router PREVIOUS_ROUTER
# Explicit maintenance of a legacy project binding:
ai-work router --cwd PROJECT --rebind --reason TEXT
ai-work repair WORKER_ID --reason TEXT --reload
```

`inspect` reads only identity/status/path/registration: no full workspace scan, no turn, no ownership or permission change. Ordinary collaboration does not become adopt. Automatic owner-to-owner question/answer forwarding is not added in this release; users/current owners can exchange the work package and evidence. Adoption is the existing explicit dispatch-control path and keeps the selected session's original path/rules. Do not audit unrelated projects or impose this Router's project facts on an external session. Authentic external input remains visible in the selected session and is synchronized by its current owner; it does not rewrite another Router's model context.

Legacy Router bindings may reflect the old open/cwd conflation. Use an explicitly established entry and idle window; do not infer the intended root from the latest task directory. Repair refuses queued/active tasks and human control, preserves the original ID and history, and requires native confirmation. On the tested backend a loaded thread ignored resume's cwd override; explicit `--reload` briefly archives/unarchives that same idle thread before resuming, reloading its instruction sources. No fork, replay or conversation-database edit is used. A failed native confirmation remains an error to inspect.

Worktree mechanics use Git directly under coordinator ownership. Claude's EnterWorktree moves the calling Claude session, so we do not use it to move the Router or pretend it created a Codex temp. Existing native WorktreeCreate/Remove hooks and `.claude/worktrees/` are not replaced or commandeered.

See [components and views](../../../docs/framework-components.md), [Desktop limitations](../../../docs/desktop-session-visibility.md), and [shared knowledge](../../../docs/project-memory.md).
