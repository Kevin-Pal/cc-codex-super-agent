> Historical proposal/handoff. Current behavior is defined by [project paths](../project-paths.md), [components](../framework-components.md) and the [documentation index](../README.md). Earlier plans are not current API or permission grants.

# Developer review guide

Preserve the goals: an accountable Router, bounded authorized execution, native session continuity, human intervention and one logical project authority. Implementation choices may improve with evidence.

Focus review on state/mutation boundaries: write admission and dispatch share a lock; queued work must use current input/knowledge; pause/manual control survives events; unknown native outcomes are inspected rather than replayed; task deadlines do not prove a native turn stopped.

For new parallel work, verify repository/worktree identities, execution directories, shared external resources, serial integration and combined checks. Confirm native Desktop discovery/interaction through an actual supported path; do not infer GUI grouping from one protocol field.

Additional context is a model reminder, not deterministic enforcement. The current guard covers named edit tools; arbitrary Bash writes and unmanaged external sessions remain coordination concerns. Return reproducible evidence, concrete scope and remaining uncertainty rather than model agreement.

See [Router principles](../router-accountability.md), [parallel design](parallel-workers-design.md), [validation](../runtime-validation.md) and [compatibility](../harness-compatibility.md).
