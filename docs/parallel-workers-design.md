# 同项目并行 Worker：隔离执行与有序集成

2026-11-02。状态：研究与建议方案，尚未安装自动 worktree 管理、资源租约、并发配置或原生项目关联适配。本轮没有放宽同工作树单写者，也没有新派发真实模型任务。

## 目前已经能做什么

0.2.2 全局默认两个执行槽，正式/临时会话类型不决定是否并行。`paths.write_overlap` 以实际登记 cwd 的路径包含关系和 `git rev-parse --show-toplevel` 判定写入重叠：同一工作树的子目录仍互斥，独立 sibling linked worktrees 可以通过。显式 independent-review 使用只读权限，可和写者并行；只读结果基于的文件版本仍要说明。

本轮用真实 Git 仓库和两个 linked worktrees、FakeNative 后端验证了现有调度器：不同树的两项任务都进入 RUNNING，同一树为 RUNNING＋QUEUED；两树修改同名文件互不覆盖，主 checkout 不变。没有调用模型，也没有验证 Desktop 归属、跨树合并的语义或真实外部资源。

因此“所有 Worker 只能串行”不准确。当前缺少的是按任务选择/准备隔离环境、登记实际目标、汇合及验收的完整使用流程；仅告诉 Worker 修改不同目录仍不会解除当前整工作树互斥。

OpenAI 官方提供 [worktree 工作流](https://learn.chatgpt.com/docs/environments/git-worktrees)，用于同项目多会话的隔离 checkout；这不等于任意几个已有 thread 自动进入工作树、自动决定正确合并或协调数据库/GPU。原生 subagent 工具也不能被当成所有独立 Worker 之间的全局文件锁。

## 建议按任务选择，避免一刀切

| 任务关系 | 建议执行方式 | 保留什么约束 |
| --- | --- | --- |
| 互不依赖的阅读/调查，结果只返回消息 | 显式只读 Worker 并行 | 引用快照/版本，避免把变化中的输入称为一致快照 |
| 可分解的代码修改 | 每个工作线/分支一个 worktree，并行实现，最后单写者集成 | 共同基线、边界/接口、分支身份、测试与合并证据 |
| 批量数据/评测，读同一输入、写不同输出 | 不强制 worktree；以后增加明确输出目录/共享资源声明 | 输入只读、输出互不重叠、不改共同状态/索引；未有有效声明时仍用保守互斥 |
| 高度耦合修改或不可拆共享写入 | 同一 Worker 迭代，或先依赖后并行 | 禁止为了并行拆成彼此互相等待的碎任务 |

## Router 协调什么，程序负责什么

Router 决定任务是否独立、接口与依赖、共享事实变化以及是否接受集成结果。程序记录精确 ID/工作树/基线，执行容量、写入与资源互斥，拒绝旧任务和未知重放。自然语言用于判断与约束，程序用于可确定的状态，worktree 用于隔离 checkout；三者互补。

第一版不要求 Worker 互聊。A 交付接口/commit 后，由 Router 将可引用的增量交给 B，或按依赖先后启动；批量重复消息以后可做去重事件通知。通知不改变权限，不能替代锁或项目事实更新。DeepSeek 的相关经验见 [研究记录](deepseek-superagent-study.md)。

Router 平常不改代码可降低一种冲突，仍需防不同 Router、人的直接回合和授权 Claude takeover 与 Worker 重叠。worktree 不阻止高权限进程写回原目录，也不隔离共享 Git 配置/对象、数据库、服务端口、GPU、缓存和远端目标；按实际目标另做资源约束，不能宣称 OS 沙箱。

## 建议的最小闭环

1. **准备。** 固定可核对的 Git 基线、工作线和独立分支；每个 worktree 在项目外的 sibling 管理目录。原工作区有未提交改动时明确选择已提交基线或经审查的快照，不自动 stash/reset，不把私有/ignored 内容批量复制。复用环境前核查 repo/branch/base 和准备回执，不仅看目录存在。
2. **派发。** 在原 Worker 原生 thread 连续性与 Desktop 可见性可证明的前提下，登记 `project_root`、`execution_cwd`、工作树/分支、基线、允许写入和必要资源。互不依赖任务先用现有两个槽试点；活动回合不迁移 cwd。
3. **执行。** Worker 只在自己的执行范围实现和本地核验，返回 commit/diff、检查、依赖与待决事项。各树内仍单写者，不让所有 Worker 同时修改中心进度文档；它们提交候选事实，由当前负责者整合。
4. **集成。** Router 指定一个既有 Worker 承担集成，自己判断和验收；用户点名 Claude 时也可由 Claude 做。集成者在受控工作区串行合并，核对实际变更和冲突，运行组合后的检查。Git 无冲突不等于业务/接口兼容；Worker READY、可合并、集成已验证和 Router ACCEPTED 不能混淆。
5. **保留。** 验收后正式 Worker 闲置保留。工作树和分支的清理与 session 生命周期分开；未合并、脏、活跃、待验收或人工接管的树不自动清理，不删除聊天，也不让自动清理破坏长期 Worker 的执行位置。

## Desktop 与项目知识是上线门槛

用户要求在原项目下发现正式 Worker、同 thread 人工介入。若简单把 thread cwd 改为新 worktree，可能影响路径索引、规则读取或 GUI 分组；不能要求用户为每个 Worker 手动新建 Project 来掩盖适配问题。

Codex 0.166.0 的 thread/start 与 turn/start 参数没有可设置的 projectId，但返回的 Thread 带 app-server 拥有的 `projectId`，`Project` 有多根 `roots[]`，并有 `thread/project/updated`、`project/changed` 通知；客户端没有设置归属的方法。2026-11-02 在一台实例上只读 `thread/list` 发现全部 thread 的 `projectId` 均为 null，Desktop 分组因此不能从该字段推断，需要在 Desktop 侧观察；该实例已有一个正式 Worker 以 sibling linked worktree 为 cwd 运行，可作为零风险观察样本（具体 ID 记在实例私有记录）。turn/start 的 cwd 覆盖会成为后续默认目录。[官方协议](https://learn.chatgpt.com/docs/app-server#start-a-turn) 支持该覆盖，但没有因此保证 Desktop 的原 Project 归属不变。优先调查原生 managed-worktree/Project 关联；若不能通过现有接口保持发现/介入，应把稳定会话入口与实际执行目标分开登记并做受控验证，不靠随意改 cwd 或猜 thread ID。

2026-11-02，另从 Desktop 专用接口只读核对现有样本：一个 sibling linked-worktree 正式 Worker 的应用层 Project ID 与原 checkout 的 Project ID 相同，执行 cwd 仍是 worktree。此例不需要增加第二根目录，说明原生返回 null 不能等同于 Desktop 未分组；没有目视截图，也不据此宣称任何新建/迁移方式均保持归属。具体 ID 与路径仅留实例回执。

worktree 内的 AGENTS.md/项目文档是版本快照，不会自动实时同步。仍保持一套逻辑权威事实和版本：中心项目记录已接受的决定，工作包带本轮基线/必要增量；分支只修改相关内容、回传候选结论，集成后刷新继续工作的 Worker。不能另建 Claude/Codex/每个 worktree 各自竞争的事实库。

## 下一轮验收范围

- 同一项目、两个隔离工作树的真实 Worker 同时有进展；同一实际工作树/资源冲突仍排队，全局容量边界仍有效。
- 两个正式 Worker 仍在原 Desktop Project 可发现、保持 thread ID 并能人工交流；恢复与续派采用正确执行路径和最新项目事实。
- 两树包含同文件不同修改、一个组合语义冲突，以及主工作区未提交变化，均能给可审查结果；集成检查不只看 merge 退出码。
- 人工接管、暂停、取消、准备中断、协调器重启和不确定派发不造成双写、自动重放或脏工作树清理。
- 数据任务另行验证输出目录与真实目标资源，不以 Git worktree 代替数据/部署互斥。

建议先实现一个项目、两个 Worker 的完整闭环，再评估可配置并发与人工跟进优先。全套 A2A、分布式锁、自动 merge/发布和跨设备调度不列为首轮条件；默认互斥只在证据充分的隔离路径上放开。
