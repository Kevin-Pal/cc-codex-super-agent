# Documentation index

This branch reviews documentation and acceptance guidance. Its public runtime source remains **0.3.0**; the private 0.4.0 interaction candidate is described separately and has not been exported or installed by this change. Documentation is not evidence of live Router adoption.

## Start here

- [Installation and rollback](../SETUP.md)
- [Human workflow](human-workflow.md) · [Local and remote topology](deployment-topology.md)
- [Components and full architecture diagram](framework-components.md)

## Working contract

| Topic | Guide |
| --- | --- |
| Formal/temp/personal sessions, retention and control | [Session lifecycle](session-lifecycle.md), [session protocol](worker-sessions.md) |
| One project entry, external sessions and managed worktrees | [Paths and ownership](project-paths.md) |
| Work packages, feedback and L1/L2/L3 acceptance | [Router prompts](router-prompts.md) |
| Human/Router responsibility and direct Claude work | [Router accountability](router-accountability.md), [direct work](claude-direct-work.md) |
| Shared project facts and on-demand instructions | [Project memory](project-memory.md), [instruction loading](instruction-delivery.md) |
| Operations, wakeup and recovery | [Runtime operations](runtime-operations.md), [communication and sandbox](communication-and-sandbox.md) |
| Tiers, quota continuity and optional web consultation | [Model routing](model-routing.md), [continuity](quota-continuity.md), [manual advisor](human-advisor.md) |

## Candidate APIs, evidence and development

- [Conversation interaction API](worker-interaction.md) separates current sync/send/steer from unshipped status/history/unread APIs.
- [Design principles](agent-design-principles.md), [decisions](design-decisions.md) and [design lessons](design-lessons.md) explain tradeoffs and TBDs.
- [Validation](runtime-validation.md), [harness compatibility](harness-compatibility.md) and [Desktop visibility](desktop-session-visibility.md) record observed results and limits.
- [Roadmap](roadmap.md), [Git workflow](git-workflow.md), [reviewed snapshots](snapshot-workflow.md) and [versioning](versioning.md) describe maintenance.

## Historical proposals and handoffs

[Parallel Worker proposal](history/parallel-workers-design.md), [architecture review brief](history/architecture-review-brief.md), [earlier Claude handoff](history/claude-review-handoff.md).

History preserves context; current guides define the contract. Move superseded phase plans into `history/` with a replacement link rather than keeping several competing current instructions. New documents should fill a real gap in this index.
