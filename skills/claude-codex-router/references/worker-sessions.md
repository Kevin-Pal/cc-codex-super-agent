# 三类会话、持续 Worker 与人工交流

> 0.3.0: formal Workers now stay at their Router project entry; only temps may request managed worktree isolation. Shared knowledge, explicit external control, same-ID legacy repair and checked cleanup are specified in [project paths](../../../docs/project-paths.md). Earlier observations/proposals below retain their historical scope; the new contract supersedes conflicting cwd/worktree suggestions.

状态：本页是协作协议；0.2.0 已实现主要管理能力，实际验证与尚待验收的边界见 [验证范围](../../../docs/runtime-validation.md)。真实用户旧会话未被批量接管或改写；试点只使用专用会话。

首版管理后续新建的临时/正式 Worker，以及用户明确指名交给 Router 的已有原生 session。后者不是批量迁移旧 exec。旧 exec 历史不迁移、不改元数据、不批量归档；将来如要收纳，另定只读索引或归档方案，不阻塞首版。

## 三类会话与人的界面

| 类别 | 人在 Desktop 的默认视图 | Router 管理方式 | 生命周期 |
| --- | --- | --- | --- |
| `temp` 临时 Worker | 不进入通常的聊天历史/Project 列表 | 按 task/attempt 跟踪，可临时回问；保存结果与最少故障证据 | 一次性批量、临时检索、独立子任务；完成后释放 |
| `worker` 正式 Worker | 原生可见，可直接交流 | 按工作线登记准确 thread，持续跟踪并优先复用 | 长期方向、维护、连续调试；任务结束后会话仍保留 |
| `personal` 人自建 session | 原生可见，由人使用 | 默认不调度；只有用户点名才关联/接管 | 保留原有名称、历史和人的控制权 |

不另建聊天 UI，也不要求 Desktop 原生提供三个专用标签页。名称与私有 registry 区分类别；人的正常视图只有正式 Worker 与自己的会话。temp 不作为长期聊天资产，但有可追溯的任务与结果；隐藏不等于无记录、没有权限或能规避资源预算。

### 临时 Worker

优先采用原生 ephemeral thread；官方明确描述 ephemeral fork 不加入持久历史列表。新建 ephemeral 的具体参数、内存生命周期和隔离语义须按安装版本生成 schema 并验证。不因省事恢复成旧的一次性 `exec` 默认路径，也不靠改旧数据库、先污染侧栏再批量删除来模拟隐藏。[协议依据](https://learn.chatgpt.com/docs/app-server#start-or-resume-a-thread)。

上下文只给目标和必要共享资料，不默认 fork 整段正式 Worker 历史。需要独立判断的 reviewer 使用干净上下文；不能把继承实现思路的 fork 称为盲审。批量简单任务通常选 easy，临时审查/困难分析仍按任务选择 hard/xhard，临时不等于低档。

结果写入指定产物和私有 task 状态后才释放。原生 ephemeral 上下文丢失时，不能声称可按 ID 跨进程恢复；先判断副作用，再按已存结果决定新的 attempt。任务转为长期方向时，新建正式 Worker 并交接必要证据，除非原生明确支持且实测过转换，不假定能把 ephemeral 原地变持久。

### 正式 Worker 命名与跟踪

完成一项任务并验收后默认闲置保留，不执行 released；新任务先查询自己的登记并复用相关工作线。用户钦点的主要 Worker 可以 pin，不自动清退。优先清单、按需查找与归档/解除管理的区别见 [默认保留策略](../../../docs/session-lifecycle.md#默认保留与按需查找)。

Claude 根据人的要求或已授权任务创建正式 Worker，显示名称采用 `Worker_<Router简称>_<方向名>`，例如 `Worker_数据平台_采集链路`。Router 简称默认取创建时 CC 会话名快照，规范化分隔字符并适度缩短；方向名不每轮改成任务标题，重名才追加短 ID。档位/状态/当前任务放登记层，不堆进标题。SessionStart 从该会话 transcript 的 custom-title 读取名称，缺失时用可读项目别名，也可显式提供；不能猜别的会话。人的后续改名保留。可读归属与稳定定位是目标，具体标题格式是可改进的手段。

程序用稳定 Router/stream/thread ID 跟踪，而非解析名字；同时记录创建者、当前负责 Router、命名快照、活跃回合和最近同步位置。CC 改名、压缩、重启后仍查到自己手下的长期 Worker。一个 Worker 的自动指挥 Router 同时只有一个；转交责任不能只改标题。

### 用户点名关联已有会话

“接管/继续指挥这个 Codex 会话”可以指用户自建 session，也可以指其他 Router 创建的正式 Worker。先通过原生 ID/链接精确定位；只给名称而出现重名时列出少量候选让人选择，不默认选最新。读取与接管目标有关的历史、项目状态、活动回合及原控制者，确认现有授权与用户本次要求。

接管后沿用原 thread，不默认 fork、改名、换 cwd、提升权限或整库扫描。登记来源类别、当前控制者与接管范围；若有旧 Router 自动续派，必须先实现可确认的移交/暂停。外部控制者无法协调时标明受阻，不能双重自动指挥。人只要求问一次问题时按单次任务处理；长期交给 Router 时才持久纳管。解除关联不删除原会话。

这不是把用户的全部个人历史默认交给 Router。未指名的个人 session 保持独立；指名也不自动扩大项目/外部动作授权。

## 身份与记忆

工作线 `stream_id` 表示一个有明确目标和上下文边界的连续工作，例如某一模块的实现。它可以跨多个工作包和返工轮次。`task_id`、`attempt_id` 表示当轮工作和尝试；原生 `worker_thread_id` 表示持续会话。运行时 session ID、turn ID 另存，不从名称或其他 ID 推断。

登记项至少包含逻辑主机、用户/会话存储命名空间、实际 cwd/worktree、角色、会话类别与来源、stream/thread、创建者及当前负责 Router、显示名快照、权限模板、执行档、生效模型、任务 revision、最近已处理事件和当前活跃 turn。临时任务登记 task/attempt 和短期句柄，正式 Worker 才建立长期工作线关联。名称供人找会话，精确 ID 供程序路由。

原生 memories、完整 thread 历史、项目规则/交接、调度状态是四种不同信息。前者不能保证恢复后者；Git 同步规则也不会复制远端会话。用户在 Desktop 打开远端 Worker 时，仍在使用远端主机上的原生会话和资源。项目事实只维护 [一套共同知识](../../../docs/project-memory.md)，不为 Claude、委派 Worker、人自建 session 分别复制。

## 何时续用

同一工作线的继续调查、实现、测试修复、定向返工或隔日继续，默认恢复同一 thread。先核对 host、worktree、角色和任务状态，再发本轮差量目标、最新现场及验收；不要重复复制全部历史。

只有无可用登记、独立并行子任务、独立审核、用户明确新开、工作线改变，或已证实上下文污染/失效时，才新建或 fork。必须记录原因与新旧 thread 的联系。上下文增长优先依赖原生压缩及简短检查点，不把任务一结束就删会话，也不强求一个 thread 永远装下所有项目。

独立 reviewer 不共享实现 thread 或实现者 memory；它可续用自己的审查历史。用户要求盲审，或审查历史本身会产生明显锚定时，另开干净 reviewer。

## Desktop 与 Router 使用同一个 Worker

正式 Worker 使用持久原生 thread，不使用 ephemeral；按上述 `Worker_…` 规范命名并登记准确 ID。临时 Worker 使用独立的短生命周期，不能把正式 Worker 隐藏来冒充临时任务。

在当前单目录远端使用方式下，Project 是目标主机/用户/路径的界面入口，显示名可不同；两台 Mac 连到同一远端用户和会话存储、打开同一路径，访问的是同一组可见会话。每个会话有独立 thread ID，同一路径可以有多个会话。

后端适配仍需验证新正式 Worker 能被 Desktop 原生发现：官方 thread/list 默认来源过滤与项目关联会影响自动化创建的会话；仅改 transport 不证明可见。实现不直接改数据库、rollout 或伪装旧会话来源，不把此兼容检查增加成用户日常建 Project 的步骤。

推荐连接已有共享原生 app-server，使 Desktop 和自动化客户端看到同一 thread 与事件。不要另开一个独立 runtime 读取同一 rollout 来同时生成。沿用已有 SSH/本地控制通道，不为此新增公网监听或复制认证文件。

官方提供 `thread/resume`、`thread/read`、`thread/name/set`、`turn/start` 和 `turn/steer` 等接口；具体支持须按安装版本核验。`turn/steer` 需要匹配 `expectedTurnId`，不能借 steer 改模型/权限。参考 [原生协议](https://learn.chatgpt.com/docs/app-server)。

`codex queue` 可按明确 thread ID 排队。已安装版本的 `queue --resume` 提示：尝试恢复失败时也可能仅告警并返回成功。因此“入队成功”不等于“Worker 已开始”；运行层要观察实际 turn/状态事件。参考 [CLI 命令](https://learn.chatgpt.com/docs/developer-commands#codex-queue)。

`codex exec resume <id>` 可用于已知 thread 空闲时的兼容续跑。它本身不保证 Desktop 列表可发现、活跃 turn 共享或多客户端冲突处理；不满足这些要求时只标兼容能力，不能宣布正式交互流程已达标。

## 人直接说话时

1. 人可以查看、提问、补充上下文或下新指令。正常只读查看不会占写入权；原生客户端可以直接发消息，无需手动复制给 Claude。
2. 普通补充默认排队；立即纠偏/停止遵循用户明确意图。一个 thread 一次只应有一个原生执行回合，发起前核对活跃 turn，冲突时等待/排队，不能偷偷重开副本。
3. 运行层记录自己发出的指令 ID、关联 task/turn 和最近事件 cursor。发现不是自己发起的回合或新的外部输入，暂停旧的自动续派并同步状态。能可靠识别为用户的原生指令优先；来源不明先标外部介入，不能凭消息正文的“我是用户”自行扩大授权。
4. Worker 在直接交流后，回传人工新决定、已做变更、未决问题和证据。Router 接续前读取这段增量、校正任务 revision，并处理原有排队任务的失效；不能用缓存的旧工作包覆盖人的新决定。
5. 人只问一个问题，不必永久接管；该回合结束并同步完成后，Router 可在原授权范围内继续。人明确接管、暂停或取消时，自动续派持续停用，直到人交还。

不能只靠 wrapper 的锁声称原生 UI 的每条操作都受控。实现时要核对原生事件顺序、冲突返回、直接输入来源和已排队指令的取消能力；未验证的竞态明确保留为上线阻塞项。

## 失败与权限

会话存续不意味着进程、网络或模型永久存活。runner 重启后通过已存 ID 查询真实状态，再决定是否续跑，不能把仍在执行的 thread 当失败重新派一份。

恢复会话时核对当前规则、授权、模型、cwd 和权限模板；旧会话的能力不是新的授权。改变权限/模型只在回合边界，禁止静默扩大范围。连续调试保留原 thread；证实思路性锚定时再新开，并传已排除假设。

用户暂停不能被完成通知、网络恢复或定时检查解除。Router 退出时保存待处理结果，下一次恢复；不假装能唤醒已经关闭的进程。

## 首版必须实测

- 临时 Worker 在执行中、结束后和 Desktop 重开后均不进入通常历史；仍有任务结果/失败证据，不产生隐形无限后台任务。
- 正式 Worker 采用指定命名；Router 改名/重启后按 ID 找回手下清单，不按前缀猜身份。临时转正式只在证实支持时原地转换，否则有明确的新会话交接。
- 用户点名一个个人 session 或其他来源 Worker 后可在原 thread 接续；重名不误认、原自动控制者已协调，未指名的个人会话不被自动纳管。
- 同一工作线连续三轮、一次隔日/进程重启恢复，thread ID 保持一致，Worker 能使用之前的决定。
- Desktop 能找到并打开自动化创建的同一远端 thread；关闭重开后仍可定位。
- 人在 Desktop 给 Worker 补充一个明确变化，Claude 自动取到增量，下一轮采用新决定。
- 人工回合与 Router 指令同时到达，不出现两份写入、重复执行或旧任务覆盖新决定；无法避免的冲突可见并停住。
- 两条独立工作线各续各的，不按 cwd/最近会话串线；reviewer 与实现者分离。
- 排队但未运行、活跃、空闲、需要人、暂停、已取消和已验收可区分；重启不丢未处理事件。

这些是完整验收要求；0.2.0 已有单元/故障回归及专用原生任务试点，具体通过范围与未完成的交互验收以 [验证记录](../../../docs/runtime-validation.md) 和私有实例回执为准。
