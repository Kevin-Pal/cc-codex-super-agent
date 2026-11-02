# Design lessons

- Reduce the person's coordination burden: a Router should translate intent into useful constraints, review real artifacts and provide concrete repair guidance.
- Preserve explicit human assignments and a cheap direct path; delegation percentage is not the success metric.
- Reuse native session identity for continuing work. Shared multi-client visibility helps intervention but is not a concurrency lock.
- Use structured task/state/event interfaces and bounded text transfer. Final-answer-first results reduce noise; they do not eliminate independent evidence inspection or prove measured token savings.
- Prefer deterministic identity, admission, freshness and recovery checks at mutation boundaries; keep semantic judgment in the Router. Unknown outcomes are not replay instructions.
- Maintain one logical project authority. Worktree documents are snapshots and need accepted-change synchronization, not three competing memory stores.
- Review native versions and capabilities; separate framework source, installed content, running daemon and access GUI versions.
- Publish reviewed generic snapshots with clean provenance boundaries. Private provider/account experience, host configuration and conversations do not belong in public examples.

Future integration and communication improvements are tracked in [roadmap](roadmap.md), [parallel design](parallel-workers-design.md) and [communication](communication-and-sandbox.md).
