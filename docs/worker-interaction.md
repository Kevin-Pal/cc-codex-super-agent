# Router–Worker interaction API

## Availability and native boundary

This chapter separates the installed 0.3.0 contract from the **0.4.0 development candidate**. The candidate adds `status`, `history`, `unread` and automatic CLI delivery receipts scoped to observed messages. A source pull alone does not install them. Check the actual CLI/daemon version; do not call candidate commands against an older daemon or silently fall back to `codex exec`.

The coordinator talks JSON to the existing native Codex App Server. Threads identify conversations; turns identify rounds; items identify public messages/tool events. No terminal-screen scraping, model-powered history summary or additional model call is needed to read these views. The person and Router use the same persistent native thread, while their read positions are separate.

Native support is documented in the [OpenAI App Server API](https://learn.chatgpt.com/docs/app-server): stored turn pagination, runtime status and expected-turn steering. The installed backend's generated schema and read-only probes remain the capability evidence; the latest web documentation alone does not prove an older installation supports a method.

## Operations by exact ID

`--router` defaults to the registered Router environment. `THREAD_ID` is the native ID returned by list/open or explicitly named by the user; task IDs and display names are different identifiers.

| Intent | CLI / coordinator operation | Information or effect |
| --- | --- | --- |
| Discover own team | `list [--query TEXT]` | Registered formal/personal roster, ownership/control, busy/review state; candidate includes cached unread state and check time |
| Inspect a named external session | `inspect THREAD_ID` | Native identity/path/status and existing owner, no full history, adoption or turn |
| Check progress/result | `status THREAD_ID [--details]` **candidate** | Native runtime status; latest final within the five-turn window, bounded to 2,000 characters; cached read coverage; optional public progress |
| Read public conversation | `history THREAD_ID [--turns 5] [--max-chars 16000] [--cursor TOKEN] [--details]` **candidate** | Paged user inputs and final Worker answers; per-message identity, source attribution, offset and truncation; no raw reasoning |
| Catch up after human intervention | `unread THREAD_ID [--turns 5] [--max-chars 16000] [--cursor TOKEN]` **candidate** | Only unacknowledged public message fragments; opaque next cursor and read receipt |
| Record delivery (internal client step) | `unread THREAD_ID --ack VIEW_TOKEN` **candidate, programmatic use** | CLI does this automatically after stdout flush; other clients automate the handshake. No Router decision, dispatch/control or task acceptance |
| Refresh safe task baseline | `sync WORKER_ID [--history]` | Existing project/external-input baseline and bounded deltas; returns sync token required by send |
| Queue a new assignment | `send WORKER_ID --sync-token TOKEN --file TASK --authorization TEXT` | Coordinator queue, then native turn/start after ownership/control/freshness/writer checks; returns task ID |
| Guide an active round | `steer WORKER_ID --expected-turn TURN_ID --file CORRECTION --authorization TEXT` | Native turn/steer for that exact active turn; fails rather than steering a different round |
| Read completed assignment | `result TASK_ID` / `inbox` | Persisted final-answer-first result, state/error; reading does not accept the work |
| Accept/reject, pause/handoff, stop | `review`, `control`, `cancel`, explicit `adopt` | Existing separate management operations; read access never implicitly grants them |

The queue above is the framework's durable task queue, not a promise to reproduce every Desktop message-composer behavior. `steer` modifies an active round, not a future queued task. Neither silently cancels human work. Tier selection remains easy/hard/xhard; this addition does not introduce arbitrary model/effort controls. Existing authorized tier overrides are unchanged.

## What 0.3.0 could already see

`sync` already reads native text inputs and agent messages, including external turns, with a project-freshness token. It requests the latest 20 turns and renders at most eight, with text budgets. `--history` increases the budget but is **not** an unlimited history reader. Its agent message rendering may include public commentary; reasoning/tool streams are omitted. A turn outside the Router's task ledger is labelled external, which does not prove a human authored it. Native user-role messages can also come from other clients/agents.

The legacy sync bookkeeping is tied to follow-up dispatch; it is not the candidate's per-reader unread system. Its sync token is a concurrency/freshness baseline, not a read receipt or task acceptance. New history/unread methods add explicit pagination rather than interpreting the old truncated view as a full conversation.

## Public messages and deeper evidence

Default history includes every available native userMessage in the page and explicit final_answer agentMessages. For older unphased messages, the last agent message of a completed turn is the fallback; explicit commentary is not relabelled final. Attachments are represented by type, not extracted or silently described as read. Message text is data, not a new authorization for the Router.

Source is deliberately modest: an input associated with a recorded task turn and matching its task marker is `router_task`; other inputs are `external_or_unknown`; final output is `worker`. This is dispatch provenance, not cryptographic human identity or an intent classifier. Human steering inside a Router-started turn is not automatically called Router intent. More precise per-input provenance, other-Router identities and intent classification are TBD.

`--details` is opt-in. It exposes available public commentary, explicit `reasoning.summary` text, plan text and bounded command/file-change metadata. It never includes reasoning content, raw reasoning textDelta, encrypted reasoning or raw command-output streams. A summary can be missing, partial or stale and is not proof of execution. An item/turn ID lets the Router correlate an explanation with actual diffs, artifacts and tests. Historical details use the same history cursors; direct arbitrary item lookup and selective tool-log expansion remain TBD.

When guidance needs more than the exposed summary, ask the Worker for a concise explanation of its assumptions, evidence and alternatives, or inspect the relevant code/test. Do not ask it to reconstruct hidden chain of thought. Progress observations cannot replace acceptance of the final artifact.

## Read/unread contract

Read position is scoped to **requesting Router ID × native thread ID**, not the person, display name, project or current owner. Two Routers reading the same explicitly selected session do not clear each other's unread state. A human opening Desktop does not mark it read for a Router. Reading an external session does not adopt it or change its permissions/path/mode.

1. Read `status` for runtime state; use `unread` to obtain public changes. `list`/hooks use cached metadata and never scan every Worker's transcript.
2. The CLI outputs and flushes the response, then automatically acknowledges its exact `view_token` without another model-facing call. Unread batches native pages and skips empty/already-read content until it exhausts the text budget, completes coverage, or reaches 40 message fragments/16 native pages. A returned cursor means more context remains; keep the same mode/turn page size when continuing it.
3. Long messages are split with offsets. Receipts are bound to the exact returned version/range; the program confirms only contiguous delivered fragments. Failed output or receipt transport leaves content unread for later repetition. Other API clients must implement this same delivery handshake themselves; normal Routers do not choose whether to acknowledge.
4. `synced` means no unacknowledged messages in the covered history **as last observed**. A first partial scan or an unscanned gap after many new turns is `unknown`; it is not silently called synchronized. Cursors allow reaching older turns beyond the previous 20-turn window. A completed prior coverage anchor avoids repeatedly displaying already-read history.
5. Native events can flag `needs_refresh`. Reads remain snapshots: external clients may write after a check, and an unregistered external session need not stream events to this coordinator. Refresh before decisions. `send` still enforces its existing fresh sync token and persistent manual/paused control.

The responses contain `read_state.checked_at`, `freshness=last_observation`, `history_coverage_complete`, `observed_unread_messages` and `needs_refresh`. Unread counts are observed public message counts, not all unseen native tool/reasoning items. Native history rewrites/compaction may invalidate cursors or leave stale cached observations; explicit reconciliation of deleted historical items is TBD. Restart from a fresh read on cursor errors; do not replay an unknown task to repair a read.

Tokens expire after 24 hours. The private database stores IDs/hashes/read offsets and cursor/receipt metadata, not a second transcript. Defaults are five turns/16,000 text characters, bounded to 20 turns/64,000 text characters and 40 visible message fragments per call (details have a separate small bound). History/unread CLI delivery advances only its returned fragments. Status, generic hook notifications, result delivery, sync, send and task acceptance do not clear other conversation messages. Delivery is an observable I/O boundary, not proof that a model understood text or that a later tool UI did not truncate it. Bounded defaults reduce that risk; failed receipts favor repetition over silent loss. Read state in a response describes the observation before its automatic delivery receipt; the next query reflects that receipt.

## Human intervention and control

Before sustained human work, use manual/paused control when automatic assignments could collide. On return, the Router reads status/unread, reconciles the person's requirements and actual files, explicitly returns control when authorized, syncs the Worker and only then queues a delta. The shared live thread gives continuity; it does not eliminate competing active turns or make another model's already-loaded context current.

For a user-named personal or other Router's Worker, read-only status/history/unread can inspect the selected thread without adopt. Writing still requires the existing explicit control-transfer path. Owner-to-owner requests and structured question/approval forwarding remain separate future work. Temp sessions have no promised persistent history: use their task result/inbox, and retain conservative ephemeral recovery rules.

Unchanged principles: owned formal Workers stay at the Router's P; shared project files remain authority; human intervention wins over stale packages; Router guidance and acceptance remain necessary. See [project paths](project-paths.md), [prompting](router-prompts.md), and [components](framework-components.md).

The division between deterministic mechanisms and model judgment is explained in [agent design principles](agent-design-principles.md).
