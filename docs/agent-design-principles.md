# Put predictable mechanics in code; reserve model judgment for meaning

This project's Router is a human-facing planner, guide and reviewer. It should spend reasoning on intent, constraints, tradeoffs, useful feedback and acceptance. It should not repeatedly decide how to paginate a list, record a read position, retry an idempotent query or remember a path invariant.

This is our implementation policy, informed by the owner's workflow and the primary sources below; it is not a claim that every agent framework must use the same architecture.

## Allocation of responsibility

| Decision or operation | Preferred owner |
| --- | --- |
| Identity/path/control validation, fixed project entry, writer admission | Authoritative coordinator code |
| Conversation pagination, budgets, delivery receipts, cached indicators | Client/runtime code with bounded work and explicit failure states |
| Registration triggers, idle wakeup, concise current-state reminders | Hooks; invariant enforcement still lives behind the API |
| Common prompt structure, relevant acceptance fields, reference discovery | Short role skill plus task-specific references/templates |
| Understand the person's intent, decompose work, choose useful scope/tier, guide repair | Router judgment |
| Resolve conflicting requirements, judge design quality, inspect evidence and accept delivery | Router, with the person for genuine new decisions |

Hooks are integration triggers, not a synonym for correctness. They can be missed or repeated. The coordinator must independently enforce important invariants and make repeatable operations idempotent. Conversely, a deterministic check cannot establish that a design satisfies a subtle human preference; retain review instead of equating passing tests with acceptance.

## Agent-facing operations should express intent

Expose a small set of useful actions such as status, unread/history, queued assignment and active-turn guidance. One action may perform several native reads or bookkeeping writes internally. Avoid giving the model a low-level protocol it must reassemble on every turn.

For example, normal unread retrieval automatically traverses native pages within its budget and records delivery after the CLI flushes the returned fragments. The model does not choose whether to run an acknowledgment command. A lower-level receipt interface exists for other programmatic clients, not as a mandatory reasoning step. A receipt failure retains unread content; it does not prompt the Router to invent a recovery workflow or repeat a task.

The runtime stops at explicit limits, returns a cursor or unknown state, and never disguises partial coverage as complete. Semantic follow-up remains with the Router: whether older history matters, which public evidence needs expansion, what guidance changes the result, and whether the artifacts satisfy the person's goal.

## Keep discovery and everyday context small

Global instruction entries identify roles, authority and the skill entrance. Skills state the essential operations and boundaries. Conditional guides explain detailed modes; scripts execute recurring deterministic work without putting their full implementation into model context. Public conversation defaults to inputs/final answers; progress summaries and tool metadata are opt-in. Project facts stay in shared authoritative files rather than another set of model-specific summaries.

Do not create a new MCP/plugin layer solely to turn one stable CLI operation into many tools. Use another packaging/interface when it demonstrably improves discovery, permission handling or interoperability. Installation location, versioned source, private runtime state and human access remain separate concerns.

## Verify the boundary, not just the prompt

Regression tests should target information loss and conflicting state: missed hooks, duplicate delivery, partial output, a changed message during reading, many new human turns, stale cursors, restart, manual control and foreign ownership. Source inspection, fake-native tests, real-native probes and actual Router behavior are distinct evidence. Measure model-facing steps, transferred context, latency and repeated/missed messages before claiming efficiency improvements.

Some behavior must remain judgment-based or TBD: interpreting an ambiguous human correction, identifying the real author behind an arbitrary native user-role message, judging a visual result, or accepting an unfamiliar integration strategy. Do not replace uncertainty with a confident regex or a long instruction checklist.

## Primary references and what we take from them

- Anthropic's [Building effective agents](https://www.anthropic.com/research/building-effective-agents) distinguishes predefined workflows from model-directed agents and recommends starting simply. We use this as architectural guidance, not as current product/API documentation; the article itself notes that its tooling landscape has changed.
- Anthropic's [Writing effective tools for agents](https://www.anthropic.com/research/writing-tools-for-agents) emphasizes coherent tool boundaries, meaningful responses, context efficiency and evaluation. We apply that to semantic CLI operations and bounded structured output, without adopting a particular vendor's runtime.
- Claude Code's [skills documentation](https://code.claude.com/docs/en/skills) describes on-demand skill bodies, supporting references and scripts. We use progressive disclosure for knowledge and executable code for recurring mechanics; loading a skill is not proof that every instruction will be followed.

See [interaction API](worker-interaction.md), [Router accountability](router-accountability.md), [instruction delivery](instruction-delivery.md) and [components](framework-components.md).
