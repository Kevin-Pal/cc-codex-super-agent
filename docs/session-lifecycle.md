# 两类 Worker 与人的自建 session

> 0.3.0: formal Workers now stay at their Router project entry; only temps may request managed worktree isolation. Shared knowledge, explicit external control, same-ID legacy repair and checked cleanup are specified in [project paths](project-paths.md). Earlier observations/proposals below retain their historical scope; the new contract supersedes conflicting cwd/worktree suggestions.

本文说明源码快照中已实现的会话管理；安装前阅读 SETUP.md 和版本兼容记录。

这是协作契约与当前设计，不把某个原生客户端版本的所有界面行为视为永久保证。临时/正式/个人与 easy/hard/xhard 是两个独立维度；一次性困难调查也可以用高档 temp，持续简单工作也可以复用正式 Worker。

| 类别 | 谁创建/默认归属 | 人在 Desktop 的日常列表 | Router 如何使用 | 连续性与结束 |
| --- | --- | --- | --- | --- |
| 临时 Worker（temp） | Router 在任务授权内创建，一次性批量/独立短任务 | 正常历史列表隐藏；不等于无审计数据 | 交明确短任务，取结果并验收，不当长期方向使用 | 原生 ephemeral；保留任务交付/验收记录，不承诺跨协调重启恢复原生上下文 |
| 正式 Worker（worker） | Router 按用户指令或已授权工作流创建，登记所属 Router 与方向 | 可见，人可观察或直接交流 | 同一方向优先续用已登记原生 thread，不每次找新 Worker | 完成单个任务后保留；暂停、人工接管、归还或解除管理，均不等于删除聊天 |
| 自建 session（personal） | 人在 Desktop/CLI 自建，默认由人管理 | 可见，人自由交流 | 只有用户点名后才 adopt 指挥；不扫描后按“最近一个”擅自接管 | 保留原 thread/名称与历史；解除纳管后仍可由人继续 |

## 默认保留与按需查找

默认生命周期是“任务验收后闲置，登记继续保留”，不需要手工设置 idle 状态，也不按空闲时长清退。明确一次性任务用 temp；需要几轮迭代就用正式 Worker，结束后仍可续用。`released` 只用于明确解除管理/移交，不是完成任务的例行动作。

新任务先在当前 Router 的登记中按方向/stream/路径查找，相关且授权仍适用时同步并复用；不用用户重新点名自己已经管理的闲置 Worker。个人或其他 Router 的会话仍需用户指名与控制权协调，不因此扫描接管全部原生历史。

用户钦点的主要 Worker 可用 `control THREAD --pin` 保留优先展示；`--unpin` 只撤销偏好，不释放、不删除、不解除 manual/paused。`list` 优先展示忙碌、待处理、置顶和近期工作线；hook 只取前十个正式/已纳管个人会话，其他可用 `list --query TEXT` 按需查询，避免每次加载全部历史。`list --all` 只额外显示本 Router 已解除管理的登记，不自动恢复权限。

Desktop 归档是人的历史管理入口，与本框架的解除管理分开；当前未把归档事件接为可靠停派信号，不自动归档/反归档。需要停止自动管理时先结束/核查任务，再显式 released。后台闲置扫描降频先 TBD，保留当前人工回合探测及写入互斥。

## Desktop 显示与生命周期分开

表中正式/个人会话“可见”指持久会话可供人发现与交流，不保证始终列在某个 Desktop Project 下。子目录、独立 worktree、原生来源过滤和应用层归属都可能影响列表；正式 Worker 完成任务不自动归档或删除，框架 pin 也不等于 Desktop pin。Project 为空先查 Recents、归档历史、登记 ID 和实际 cwd，不据此重建会话或重跑。详见 [显示与排查边界](desktop-session-visibility.md)。

## 正式 Worker 的名称和身份

默认可读标题 `Worker_<Router简称>_<方向名>`。Router 简称来自创建时的 Claude 会话名，可规范化分隔符并缩短；只有重名时才附短标识。人改过的标题应保留。标题不是唯一身份：登记原生 thread ID、所属 Router ID、项目入口/实际工作树与相关任务。

同一方向优先续用登记会话，用户直接向 Worker 提出的新决定要进入后续同步。不要用新的同名 thread 伪装成延续，也不以一段 memories 摘要替代原生上下文。确需新会话时说明原因并保留旧工作关系。

## 人工介入与接管

人可同时通过 Claude CLI 与 Router 对齐目标，通过 Desktop 观察/补充正式 Worker。两端看同一历史不等于可以无条件同时发送：Router 自动续派前刷新相关项目事实、人的新输入、活跃 turn 与同步位置；旧工作包已失效时修订，不能覆盖人的决定。

重大人工接管使用 manual/paused；保留暂停，直到人明确交还或当前维护者按已授权流程归还。普通补充信息也不能被后台事件当成没有发生。正在运行的回合需要按精确 turn 纠偏/取消，不能打断后来的人类回合。

用户可以指名一个自建 session 或外部正式 Worker 交给 Router。先用可定位的主机/用户/项目和原生 ID 确认目标，保留原名；有其他 Router 所属、活动 turn 或待处理任务时先协调移交，不抢占、不猜 ID、不暗中 fork。接管身份不自动扩展原任务的授权范围。

## 结束、结果和恢复

Worker 的任务可以 READY/BLOCKED/FAILED，但只有当前 Router/direct maintainer 核查实际产物与证据后才接受。正式 Worker 一个任务完成不等于关闭整个长期方向；temp 退出也不应丢掉可审查结果和来源。

未知派发、连接中断或超时不代表没有副作用，也不意味着原生 turn 已停止。先核查真实回合与文件，再决定恢复、重试或人工处理。临时会话缺少重连能力时，不把正式 Worker 的恢复承诺套过去；用户也不应仅因回传丢失就重跑昂贵任务。

同一个原生存储中的项目入口帮助发现会话，显示名可以不同；跨主机、用户、CODEX_HOME 或不同原生实例不能只凭路径同名推断共享。个人 session 未被纳管时不受协调器单写者锁完全覆盖，仍需现实中的写入协调。
