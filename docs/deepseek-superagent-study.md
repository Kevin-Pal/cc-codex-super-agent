# DeepSeek Super-agent：可借鉴机制与本项目的区别

研究说明：本文区分外部架构启发与当前源码能力；没有引入或运行DSH/DSH+依赖。

2026-11-02。研究记录，不是安装/启用第三方插件或变更生产调度的指令。本轮下载源码、阅读相关设计/实现与并发测试；没有安装依赖、启动 DSH、接入账户或运行其模型任务。

## 核查材料

- DeepSeek 官方组织的 [dsh-superagent-prototype](https://github.com/deepseek-ai/dsh-superagent-prototype)，固定版本 `6337fc823ce20251c8de8085948165c81aaa701e`。README 明确它是研究原型，和文章/内部实现不完全相同。
- 文章 *Exploring Super-agent Design: Towards a More Autonomous Agent System* 的 [作者 X 入口](https://x.com/DeepSeekHarness/article/2116857257245987236) 本轮返回403；阅读了 [署名公开转录](https://threadnavigator.com/thread/2116857257245987236/)，它自称中文原文的机器翻译。文章观点和下面源码证据分开；未声称已直接核验中文原文或复现实验。
- [执行文档](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/003-execution.md)、[提示组织](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/004-prompts.md)、[架构](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/007-architecture.md)；同时查看 `src/executor/dsh.ts` 的 WorkerSlots/prepareDirectory、`src/app/sessions.ts`、`prompts/dispatch.md` 和 `tests/runtime-concurrency.spec.ts`。
- 独立社区插件 [dsh.plus](https://github.com/zhaimingyou/dsh.plus)，版本 `c7326eee9e1ce4019af2c130e2e6b2174e416e00`，也已下载阅读 host 路由。它是只读插件目录，不是 Super-agent 调度器；无需把它装进现有 Claude/Codex 环境才能研究原型。

## 文章对当前问题最有用的观点

署名转录提出：独立任务通常不需要 Worker 点对点对话；相关工作可以接收共同事件，少量跨任务协调交给 Router。它也将常见确定性路由交给代码，长内容通过摘要、ID 与按需回读组织。本文据此考虑事件与资源约束，不能从“共同收到事件”推出文件写入已经加锁。文章的试验是简化/合成工作负载，不作为本项目并发加速或代码质量收益保证。[文章转录](https://threadnavigator.com/thread/2116857257245987236/)。

## 从原型提取的工程经验

| 已读机制 | 本项目可以借鉴什么 | 不直接照搬什么 |
| --- | --- | --- |
| Ticket 关联持久 Session 和独立目录，prepare 可调用 git worktree；重试继续原目录/会话 | 会话、任务、执行工作区分别登记，隔离并行修改并保留连续性 | 不要求每个小任务都新建工作树；也不把目录存在当作已完整准备的证据 |
| WorkerSlots 在异步启动前占槽，人工唤回优先且有额外槽 | 新任务、启动和已有任务跟进应有明确容量与优先级 | 不默认越过本机/GPU总预算；优先队列可先于“额外槽”落地 |
| 报告与动作先存储再执行；恢复时核查已有目录、Git/外部状态 | 新工作树创建、派发与集成需要可恢复回执，未知结果先查证 | 不因一次超时自动重放 merge、部署、外部消息或昂贵实验 |

以上执行事实依据 [003 Execution](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/003-execution.md)，容量预留实现见 [WorkerSlots](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/src/executor/dsh.ts)。

原型把可编辑团队提示、按需技能和程序校验分开，并记录自定义提示所基于的默认版本，升级时提示差异；这适合本项目后续分发。它也在提示里限制主会话长等待，让回传事件驱动下一轮。我们的短入口/按需参考、asyncRewake、READY 与验收分离可以继续沿用，不需要为学习它重造 UI 或立即安装完整运行栈。[004 Prompts](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/004-prompts.md)。

## 我们有意保留的不同目标

用户进一步确认 Router 要替人承担判断和验收，模型档位不自动改变这项目标；借鉴调度/隔离实现，保留自身职责，见 [责任与程序优先原则](router-accountability.md)。

原型的主会话提示非常克制：只作路由，避免代码调查、技术决策和替 Worker 写实施/验收计划。我们的 Claude 还承担理解人的隐含要求、提示约束、亲自验收、设计和最终加工，因此不能照抄这组禁令；较强 Router 模型的使用经验也不能被“轻量 Router 已足够”直接推翻。[原型派发提示](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/prompts/dispatch.md)。

本项目已经确认的三层责任是：**Claude 亲自做自己的本职；用户点名 Claude 的工作亲自做；Worker 不足时提供有实质内容的诊断、设计和引导。** 默认工程委派、有限直接路径与用户指定可以共存。评价目标是最终交付和人的负担，而不是委派比例。[Claude 亲自工作](claude-direct-work.md)。

文章转录描述 Worker 不直接面向人，但公开原型的执行文档允许人直接在 Executor Session 发消息。本项目明确保留 Desktop 与 Worker 的人工交流入口，需同步真实控制权；不把文章和原型混成一个不可变规范，也不取消已经验收的双入口。

## 建议优先级

1. 先补 [隔离并行与集成设计](parallel-workers-design.md)：实际写入范围、worktree、合并与共享资源，以及 Desktop 中的发现/介入验收。
2. 再评估并发上限可配置、已有工作线/人工跟进优先、相关工作线的简短事件通知。事件是事实，不携带新的授权；暂停/人工控制优先。
3. 大范围主动监听、自动执行、独立模型 Watchdog、跨设备弹性调度和完整问答桥继续 TBD。先看真实瓶颈，不一次性复制另一套平台。

少概念、少常驻规则、默认安静、只把有用结果和必要决定交给人，也应约束我们自己的框架复杂度。[原型设计原则](https://github.com/deepseek-ai/dsh-superagent-prototype/blob/6337fc823ce20251c8de8085948165c81aaa701e/docs/000-philosophy.md)。
