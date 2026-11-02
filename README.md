# CC–Codex Super Agent

[简体中文](README.zh-CN.md)

**Claude Code plans, guides and reviews. Codex executes in reusable Worker sessions.**

Explain your goal to one Claude Code Router. It directs Codex, checks the work and delivers the result. You can also open the same persistent Workers in Codex Desktop to inspect progress or intervene.

`You ↔ Claude Code Router ↔ Codex Workers`

This is for people who already use both harnesses and want less task handoff, durable context and a clear place for human review. It includes coordination rules, on-demand skills and a small runtime built on native Codex threads.

## Get started

Use Python 3.11+, Git, working Claude Code and the native Codex backend on one macOS/Linux execution host and user. The shared native control endpoint must be available; see [setup](SETUP.md) for checking it and installing safely.

```sh
git clone https://github.com/Kevin-Pal/cc-codex-super-agent.git
cd cc-codex-super-agent
PYTHONPATH=src python3 -m claude_codex_workflow.cli install --role both
PYTHONPATH=src python3 -m claude_codex_workflow.cli install --role both --apply
ai-work doctor
```

The first install command previews changes. Applying adds owned instruction blocks, role skills, the `ai-work` CLI and coordination hooks. Provider/authentication/privacy settings remain outside this installer.

1. Start Claude Code in your project directory and load `/claude-codex-router`.
2. Describe the goal and boundaries. The Router delegates execution, guides fixes and reviews delivery.
3. Open that same project path in Codex Desktop to see persistent Workers and your own chats. Human intervention and control are explained in the [session guide](docs/session-lifecycle.md).

Local use and remote use share this workflow. For a remote execution host, use SSH/tmux for Claude and Desktop Remote for Codex; a computer used only for access needs no framework installation.

## Learn more

- [Setup, permissions and rollback](SETUP.md)
- [Components and architecture diagram](docs/framework-components.md) · [Project paths and ownership](docs/project-paths.md)
- [Work packages and acceptance](docs/router-prompts.md) · [Conversation APIs](docs/worker-interaction.md)
- [Observed validation and limits](docs/runtime-validation.md) · [Contributing](CONTRIBUTING.md)

The public runtime source is **0.3.0**. Documentation labels the unshipped 0.4.0 interaction candidate separately. Same-tree writes currently queue; isolated temp worktrees are optional. Check the validation guide for native-version and recovery limits.

Inspired by DeepSeek's [Super-agent exploration](https://x.com/DeepSeekHarness/article/2116857257245987236). This is an independent Claude Code + Codex implementation with no DeepSeek/DSH dependency or affiliation.

[MIT license](LICENSE).
