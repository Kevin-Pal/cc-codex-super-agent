# Human workflow

Choose an execution host with the project entry path, Claude CLI, Codex backend and framework under the same user/session storage. Install the eventual framework once for that execution user, not once per access computer.

| Access | Router interaction | Worker interaction |
| --- | --- | --- |
| At the execution host | Enter the project and use Claude CLI | Add the local project in Codex Desktop |
| From another computer | SSH to the host, enter tmux and the project, use Claude CLI | Use native Desktop Remote to select the same remote user and project path |

In SSH mode the Claude CLI process runs on the execution host; the access terminal displays it. The access host needs no framework Worker-role installation. Native connection setup and authentication are still required. Project labels can differ; the remote host, user, session storage and entry path must identify the intended project.

For long tasks, an always-on execution host plus tmux improves continuity. tmux preserves the terminal across SSH disconnections; it does not make a powered-off host execute work. A closed Router is not an invisible planning agent: dispatched Workers may finish within scope, with review waiting for the Router's return.

Use the Router to clarify goals and review delivery. Use Desktop to observe or directly steer a formal Worker when useful. Inform the Router of control changes; resume automatic follow-up only after synchronizing the current thread and shared project facts.

If either side's quota or service is temporarily unavailable, the other may work independently within an explicit scope, without another concurrent writer. Reconcile decisions, actual changes and evidence when service returns. This is a continuity rule, not a claim of implemented automatic quota detection.

Logs may aid later diagnosis, but they remain private instance data. Report task/thread identifiers, version, timestamps, state transitions and a sanitized reproduction rather than posting raw conversations or credentials.
