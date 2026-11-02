# CC–Codex Super Agent

[English](README.md)

**Claude Code 负责理解、规划、指导和验收，Codex 在可持续复用的 Worker 会话里执行。**

你主要与一个 Claude Code Router 对话，由它安排任务、检查结果、整理交付。你也可以在 Codex Desktop 打开同一个正式 Worker，观察进度或直接介入。

`人 ↔ Claude Code Router ↔ Codex Workers`

适合已经使用这两种 harness、希望减少任务交接与人工盯进度的人。项目提供协作规则、按需加载的 skill，以及基于 Codex 原生会话的小型协调运行层。

## 开始使用

在同一台 macOS/Linux 执行设备、同一用户下准备 Python 3.11+、Git、可用的 Claude Code 和 Codex 原生后端。需要可用的共享原生控制端点，检查方法及安装说明见 [SETUP](SETUP.md)。

```sh
git clone https://github.com/Kevin-Pal/cc-codex-super-agent.git
cd cc-codex-super-agent
PYTHONPATH=src python3 -m claude_codex_workflow.cli install --role both
PYTHONPATH=src python3 -m claude_codex_workflow.cli install --role both --apply
ai-work doctor
```

第一次安装命令只预览改动；确认后第二条执行安装，加入本框架管理的指令块、角色 skill、`ai-work` 和协调 hooks。安装器不调整供应商、认证或隐私设置。

1. 在项目目录启动 Claude Code，加载 `/claude-codex-router`。
2. 说明目标和边界，由 Router 委派执行、指导返工并验收。
3. 在 Codex Desktop 打开同一路径，查看正式 Worker 和自己的会话。人工介入及控制权见[会话指南](docs/session-lifecycle.md)。

本地与远程的使用方式基本一致。远程执行时用 SSH/tmux 访问 Claude，用 Desktop Remote 访问 Codex；仅负责访问的电脑无需安装本框架。

## 进一步了解

- [安装、权限与回滚](SETUP.md)
- [组件与架构图](docs/framework-components.md) · [路径与归属](docs/project-paths.md)
- [工作包与验收](docs/router-prompts.md) · [会话交互接口](docs/worker-interaction.md)
- [实际验证与限制](docs/runtime-validation.md) · [参与贡献](CONTRIBUTING.md)

当前公开运行源码为 **0.3.0**；文档将尚未发布的 0.4.0 交互候选单独标明。同一工作树的写任务目前排队，temp 可按需使用隔离 worktree。原生版本及恢复边界见验证记录。

架构受 DeepSeek 的 [Super-agent 探索](https://x.com/DeepSeekHarness/article/2116857257245987236)启发。这是 Claude Code + Codex 的独立实现，不依赖或隶属于 DeepSeek/DSH。

[MIT 许可证](LICENSE)。
