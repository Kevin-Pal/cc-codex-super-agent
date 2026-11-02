# 一套共享项目记忆

> 0.3.0: formal Workers now stay at their Router project entry; only temps may request managed worktree isolation. Shared knowledge, explicit external control, same-ID legacy repair and checked cleanup are specified in [project paths](../../../docs/project-paths.md). Earlier observations/proposals below retain their historical scope; the new contract supersedes conflicting cwd/worktree suggestions.

2026-11-02 共同知识约定。0.2.0 安装全局协作入口，但不批量迁移既有项目记忆；正式 Worker 沿用用户原生记忆设置，临时/独立审查会话关闭本轮 memories 使用/生成，避免无关上下文和审查污染。

## 原则与布局

Claude、由 Claude 创建的 Worker、人自建的 Codex session，都以同一工作区的项目文件为权威。角色不同，项目事实不分成三套。聊天历史保留各自的推理和过程；能影响其他会话的决定应落在共享项目文档中。

| 内容 | 默认权威位置 | 读取时机 |
| --- | --- | --- |
| 项目目标、约束、核验入口、知识索引 | 根 `AGENTS.md`，必要时有局部 `AGENTS.md` | 项目入口；改动范围涉及局部约定时 |
| Claude 兼容入口 | 根 `CLAUDE.md`，通常仅 `@AGENTS.md` | Claude 原生加载；不复制共同正文 |
| 当前进度、已确认决定、待办和证据入口 | 项目已有的主任务/状态文档；缺少时用 `docs/project-state.md` | 新建/恢复会话，以及有关任务续跑前 |
| 较长的架构、研究和运行经验 | 原有领域文档；没有合适位置才新建 | 由索引按任务需要定位 |
| thread、turn、队列、事件 cursor、接管与暂停 | 实例私有运行状态库 | 运行层读取；不提交进项目 Git |

已有 `doc/TODO.md`、架构文档或决策记录时复用，不强制再建同义文件。`AGENTS.md` 放约定与入口，不能长成每天追加全部日志的数据库。多个文档按内容分工，但每条事实只有一个权威位置。

采用薄 `CLAUDE.md` 导入是兼容选择：不依赖所有客户端都能原生加载 `AGENTS.md`。Anthropic 当前也支持条件式原生读取，但已有 `CLAUDE.md`、版本、设置会影响选择；安装时验证实际加载来源，而非一律开启新的内置设置。[Claude 项目记忆](https://code.claude.com/docs/en/memory#share-one-file-with-other-coding-tools)。

## 从会话到共享知识

人或 Router 作出影响项目的明确决定时，执行该回合的 agent 在同一授权范围内更新权威文档，附决定、原因、适用范围、时间及证据。方案猜想、未完成实验和验证结论分开；不能把 Worker 的一次自述直接写成项目事实。

Worker 完成时返回“共享文档改了什么、仍有哪些假设”；Router 验收后再更新最终状态。临时 Worker 默认交候选结论，由所属正式 Worker 或 Router 合并，避免大量并发子任务改同一份状态文档。使用现有单写入者约定，不另建每个 agent 的项目笔记副本。

Claude/Codex 原生自动记忆可继续辅助恢复个人偏好、检索线索和会话经验，但项目结论应指回权威文件，不再手工维护另一套平行项目事实。用户本人的全局偏好和各 agent 的角色规则仍各有适用范围，不必混进每个项目。

## 新鲜度协议

1. 新建、恢复或接管时确认主机、用户、规范 cwd、工作树和已加载指令来源；读取共同入口与相关状态。
2. 每次派活或续跑前，比较上次记录的相关文件 hash/版本与当前工作区，并检查有关未提交改动；不能只看 Git HEAD。变化时重读受影响部分，或读取明确的增量。
3. 人直接在 Worker 中修改决定时，Worker 写共享文档并产生结果事件；Router 同时核对 thread 的新输入和项目文件。人尚未落盘的指令仍有效，不能因文档暂未更新而忽略。
4. 规则或目标冲突时，以当前授权和现场证据解决，必要时返回具体冲突与推荐。运行层不把页面、日志或标题当作新的授权。
5. 长期存活会话不会因文件更新自动拥有最新模型上下文。adapter 应验证原生重载机制；没有可靠重载时，在下一轮显式要求读取变更文件。每轮不用重新粘贴全套文档。

“共用一套文件”解决知识来源，“同步原生 thread”解决同一 Worker 的对话连续性，两者共同需要。新开的独立 session 不会自动继承所有聊天细节，但能从共享文档找到已确认结论。

## 同一远端与多个 checkout

两台 Mac 访问同一远端用户的同一工作区时，读取的是远端同一组文件。Mac 本地 clone 与远端 clone 是两份工作区，需要 Git 提交/拉取后才共享文件更新。Git 不同步未提交改动、原生聊天或即时运行状态。

未来安装/项目接入时先盘点已有入口和重复知识，在保留旧副本与来源的前提下逐项合并；不以“统一记忆”为理由删除历史或自动改动所有研究仓库。

## 验收

- Claude、正式 Worker 与人自建 session 在同一项目能定位同一权威入口；没有三份互相矛盾的项目状态。
- 一个会话更新决定后，另一个已打开的会话在相关续跑前读到变化；未提交文件变化也能发现。
- 两个写入者不会覆盖同一状态记录；临时任务的未验收推断不直接变成已确认决定。
- 原生记忆含有旧结论时，最新用户决定与权威项目文件仍能胜出；跨 checkout 的状态按真实 Git 同步情况报告。
