# Continuing Worker follow-up draft

Use the registered native thread, not a fresh Worker. This is a proposed format, not an implemented CLI schema.

- Stream and Worker: <stream_id and exact worker_thread_id>
- Current task revision and last processed event: <verified values>
- Direct human input since last handoff: <adopted changes, or none>
- Shared project knowledge changes: <relevant file/version or uncommitted delta; read changed sources>
- This round's delta: <next goal or precise repair feedback>
- Changed authorization, paths or acceptance: <only changes; otherwise preserve>
- Tier: <preserve, normally hard; state reason for a change>
- Delivery: <new evidence, artifacts and remaining decisions>

For repair, state the original requirement, observed discrepancy and required recheck. Do not replace specific feedback with a repeated generic warning. Keep identifiers and cursors tool-supplied where possible.

If another turn is active, queue ordinary follow-up. Do not start a second executor. Steer/interrupt only for an intentional immediate correction, targeting the actual active turn. If the scope has changed enough to require a new thread, state why and preserve a short handoff.
