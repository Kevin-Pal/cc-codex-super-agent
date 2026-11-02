# CC–Codex Super Agent maintenance

This repository is the public-facing, MIT-licensed source snapshot for a Claude Code Router and Codex Worker workflow. It is independently developed, inspired by DeepSeek's Super-agent ideas, and has no DSH runtime dependency.

- Work directly on the user's request. Explicitly delegated work is already delegated; do not summon another model solely for confirmation.
- Read current files, status and relevant state before changing them. Use codex/<topic> for work branches; preserve unrelated work and coordinate real write conflicts.
- Keep project authority in this file and linked docs. CLAUDE.md imports this entry. Do not create competing Claude/Codex project facts.
- Preserve Router guidance, independent evidence review and acceptance. READY is not acceptance; semantic judgment and deterministic state checks have distinct jobs.
- Never import private repository history, deployment state, real project memories, account/provider settings, credentials or chat logs. Use synthetic fixtures. Review the complete outgoing history, commit identities and source archives.
- Public updates are reviewed snapshots or generic changes. Never merge an operator's private branch to synchronize; keep provenance mappings in private operations records. See docs/snapshot-workflow.md.
- The owner performs repository visibility changes. Do not publish packages/tags/releases or add publication automation unless explicitly requested. Cloning or testing does not authorize installation into a real account.
- Keep runtime behavior, observed evidence and future proposals distinct. Record tested harness versions and unknowns in docs/harness-compatibility.md; do not promise permanent API/model compatibility.
- Preserve unrelated global instructions and settings. Internal Claude provider/auth/privacy maintenance is outside this project. Public installation changes only owned blocks/hooks; unfamiliar generation systems need explicit integration.
- Run proportionate tests. For this runtime: PYTHONPATH=src python3 -m unittest discover -s tests. Before a public push also run python3 tools/check_publication.py --history; do not bypass a finding without review.

Read README.md, SETUP.md, docs/README.md, docs/project-state.md and the task-relevant guide. Superseded plans belong in docs/history/ with a replacement link. Local pre-push hooks are optional assistance, not server-side enforcement. See CONTRIBUTING.md.
