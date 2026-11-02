# Harness 版本与兼容记录

## 原则稳定，接入能力随版本核对

Router 负责理解、指导和验收，Worker 负责授权范围内的执行；持续工作续用原生 thread，共用一套项目事实，保留人的接管与暂停。这些是工作流契约，不绑定某个 Claude/Codex 版本或模型名称。

运行适配不能承诺永久版本无关。当前实现连接已有原生 control socket，并在 initialize 时启用 experimentalApi；协议字段、事件、ephemeral 恢复、权限语义和 Desktop 项目关联需要按实际版本验证。Claude 的 hooks、asyncRewake、技能恢复及设置加载也属于接入能力。Unix socket 路径与 provider/隐私例外留在实例配置，不作为跨平台通用常量。

OpenAI 的[官方协议文档](https://learn.chatgpt.com/docs/app-server#message-schema)明确生成的 schema 对应运行该命令的 Codex 版本，并区分[实验接口](https://learn.chatgpt.com/docs/app-server#experimental-api-opt-in)。Claude 的 [hooks 文档](https://code.claude.com/docs/en/hooks)定义 asyncRewake 等事件行为。文档属于参考，不能替代已安装版本与实际观察。

## 已观察的组合

| 核对日期 | 框架运行版 | Claude Code CLI | Codex CLI | 实际连接的原生后端 | 验证范围 |
| --- | --- | --- | --- | --- | --- |
| 2026-11-03 | 0.3.0 | 2.1.316 review CLI | 0.166.0 | Same existing native backend; generated schema and real protocol probes | Mac/Linux130 public-snapshot tests (125 shared), clean Git source-archive installation/rollback; real isolated read-only temp/cleanup and same-ID/cwd/policy reload; GUI build not collected |
| 2026-11-02 | 0.2.3.post1 源码快照 | 基础组合如下一行 | 基础组合如下一行 | 沿用已验证适配，无新增真实模型调用 | Mac/Linux各100项隔离回归，包括公开安装保留性与发布检查；源码归档安装单独验证 |
| 2026-11-02 | 0.2.3 | 2.1.316 | 0.166.0 | initialize 报告 Codex Desktop/0.166.0，Linux | 原生只读连接、最终 daemon/current 一致；既有真实 Router 交互由用户回收；Mac/Linux 各95项隔离假原生端回归 |

此行是已观察组合，不是最低版本要求、完整支持矩阵或对更新版本的保证。CLI 和正在运行的后端分别取证；不能用 PATH 中的 CLI 版本推断后台进程版本。访问端 Desktop GUI 的独立应用 build 本次未采集，不由后端 userAgent 或 CLI 版本代填。Mac 的假原生端测试不能替代 Mac 原生端的全流程试点。

此前框架 0.2.0–0.2.2 的功能证据保留在 [设计决策](design-decisions.md) 和实例记录中；没有当时独立采集的 Claude/GUI 版本就写未记录，不拿今天的版本倒填。公开快照0.2.3.post1基于上述运行实现，另包含发布边界/安装保留性检查；不把源码导出等同于又跑过一轮真实模型或原生GUI联调。

## 后续怎么留历史

框架升级、Claude/Codex 升级、后端替换或相关故障时，追加一个有日期的观察；原记录保留。实例回执记录执行端/访问端角色、各组件实际版本、框架源码 commit、安装内容 hash、运行内容 hash、能力探测/验证结果、限制和回滚。用户模型选择及供应商设置不等同于 harness 版本，不写入通用兼容表或固定套餐承诺。

源码 HEAD、已安装包和运行 daemon 分开记录。文档提交不自动重装；daemon_current_matches 只证明当前链接与运行内容一致，不证明源代码 HEAD 已安装，也不证明协议或模型行为正确。

小版本变化先做只读版本与能力检查，按变化复核相关边界，不必每次重复所有真实任务。协议/会话/通知等边界变化时，再用隔离合成任务验证正式会话续用、temp 生命周期、结果与异常处理；涉及 Desktop 发现/介入或 Claude 空闲唤回时，补对应原生交互观察。未知能力明确报告，不静默重开运行时或回退到旧 exec 路径。

当前 doctor 已能回报框架与原生端信息；完整自动版本采集、schema 指纹/差异和多版本 CI 矩阵留 TBD。本次仅补维护记录，不新增常驻 hook、自动升级器、强制版本门槛，也不改用户现有自动更新设置。
