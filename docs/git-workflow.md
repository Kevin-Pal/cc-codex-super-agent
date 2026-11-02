# 两端 Git 协作

日常有两种对等维护入口：远端 Linux 的 tmux + Claude Code（由 Claude 调用 Codex），以及本地 Mac 的 Codex Desktop 直接维护。它们维护同一个 Git 仓库，不通过同步整个家目录或聊天记录协作。

## 开工

先读 `AGENTS.md`、最新交接和实施计划，然后执行：

```sh
git status --short
git log --oneline -5
git fetch origin
```

工作区干净且当前分支可以快进时执行 `git pull --ff-only`。有未提交内容或分支分叉时，先查明归属；不得自动 stash/reset 或覆盖另一端改动。新工作使用主题分支，Codex 默认 `codex/<topic>`。同一工作树同时只有一个写入者；需要并行时各用 worktree 和独立分支。

## 收尾

1. 审查实际差异和拟纳入的路径，排除凭据、个人记忆、运行状态和机器配置。
2. 运行与改动相称的检查，明确哪些只是计划、哪些已实测。
3. 有意义的变更更新 `CHANGELOG.md`，需要跨端接手时写简短交接。
4. 提交本次明确路径并推送当前分支；完成审查后再整合到 main。
5. 另一端拉取后先检查提交和工作区，再继续修改。

按当前维护者授权提交已审查的通用内容；每次推送前检查文件、提交身份和完整outgoing history。仓库访问权不等于部署、外发日志或操作账号配置的授权。

## 记忆与安装

Git 跟踪规则源，模型上下文不会随 push 自动互通。持续 Worker 的原生 thread 留在目标主机，Desktop 通过远端连接访问；session registry 和 task/turn 状态是私有运行数据。交接应给可定位的 stream/thread、最近事件、人工新决定、未决事项、目标 commit 和验证证据；不能只说“看上一会话”，也不把完整会话复制进 Git。

共同项目知识按 [共享记忆设计](project-memory.md) 维护在各项目自己的权威入口/文档中；不复制进本框架仓库。两台 Mac 打开同一远端目录时共用远端文件；本地 clone 与远端 clone 的文件更新仍要通过 Git。同一 Worker 的聊天同步和不同 agent 的共同项目知识是两条独立的连续性机制。

`git pull` 不会把 `rules/` 自动覆盖到 `~/.claude/CLAUDE.md`、`~/.codex/AGENTS.md` 或共享记忆源。未来部署必须先比较、备份、合并和验证，并在实例侧登记已安装的 commit。

源码更新不自动安装。需要部署时按SETUP.md预览合并，在实例私有回执记录实际安装与运行版本；公开代码更新不代表可以改变生产会话或账号配置。
