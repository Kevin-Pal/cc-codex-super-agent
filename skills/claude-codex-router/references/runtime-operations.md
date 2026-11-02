# Runtime 操作

入口 `ai-work` 使用 Python 3.11+ 标准库，无额外模型 API key；接入当前用户已运行的 Codex 原生 Unix control socket。协调进程在首次操作时启动，不另起模型执行器、不监听公网。

## 调用

Claude 的 SessionStart hook 提供 `CCW_ROUTER_ID` / `CCW_ROUTER_NAME`；CLI 在缺少 `CCW_ROUTER_ID` 时回退到 `CLAUDE_CODE_SESSION_ID`，也可明确指定 `--router` / `--router-name`。UserPromptSubmit 会补登记旧会话并刷新名称/cwd。推荐先 `/rename` 一个简短方向名。显示名 `Worker_<Router简称>_<方向名>` 默认沿 CC 标题，分隔字符规范化、过长部分缩短，重名才追加短 ID；稳定 thread ID 不受改名影响。

- `doctor`：查看原生服务、版本、运行中 daemon 的 release、`current` 及二者是否一致，以及实际 easy/hard/xhard 映射。不可用时先恢复已配好的原生服务，不自动退回独立 headless runtime。
- `open --stream KEY --direction NAME`：创建/续用正式 Worker；`--kind temp` 创建短期任务，临时/正式与模型档位独立。
- `list --router ID [--query TEXT] [--limit N] [--all]`：只查该 Router 登记的正式/已纳管个人会话，按忙碌、待处理、pin、最近活动排序，不加载聊天历史。query 匹配名称/stream/路径/ID，all 额外显示已解除管理的登记而不恢复它们；temp 结果仍查 inbox/result。`sync THREAD --router ID`：状态、新增/变化的输入与结果、项目知识摘要和 sync token；默认不反复输出已确认的整段历史，必要时 `--history` 查看最近回合。
- `send THREAD --router ID --sync-token TOKEN --file PATH --authorization REF`：派发；`--text` 可替代文件。`--minutes` 默认 45，从实际 RUNNING 起算；`--queue-minutes` 默认 45，单独限制排队时间。默认按内容生成幂等键；确需重复执行同样指令时明确给新 `--key`。排队期间外部输入/知识改变会阻塞旧任务，先同步再发修订工作包。
- `result TASK --router ID [--wait SECONDS]` / `inbox --router ID`：真实状态和结果。`review TASK --router ID --verdict accept|reject --note TEXT`：记录 Router 验收；Worker 不自验收。
- `adopt THREAD --router ID --router-name NAME`：用户点名的已有个人/外部 session，保留名称与原 thread。已被其他 Router 管理时需先处理其任务，再用 `--from-router OLD_ID` 显式移交。
- `control THREAD --router ID paused|manual|automatic|released`：暂停、人工接管、交还或解除管理；解除不删除会话。`cancel TASK --router ID` 只针对该任务实际 turn。
- `control THREAD --router ID --pin|--unpin`：设置/撤销当前登记的主要 Worker 展示偏好，不更改 control mode，不解除暂停或人工接管。正式 Worker 任务完成后默认保留；idle 从实际任务/回合派生，不是额外手动状态。
- `steer THREAD --router ID --expected-turn TURN --text TEXT --authorization REF`：有意立即纠偏时使用，严格匹配活跃回合；不在 steer 中切模型/权限。
- `direct EXACT_FILE --router ID --reason TEXT`：最多十分钟的微任务文件例外，必须有立即核验；不是申请目录级绕过。
- `takeover --router ID --scope PATH [--scope PATH ...] --reason TEXT [--hours H]`：经用户授权的 Claude 临时执行范围，适用于明确点名 Claude 的优化/设计/实质实现，也适用于 Codex 暂不可用；不要求额度失败或重复确认。默认 2 小时、最多 8 小时；`--status` 查看、`--release [--note TEXT]` 结束。见 [Claude 亲自工作](../../../docs/claude-direct-work.md) 与 [额度连续性](../../../docs/quota-continuity.md)。
- `daemon --stop`：只停止本框架协调进程，保留原生 Codex 和历史；有待执行/运行中的 temp 或超时后仍活跃的原生回合时拒绝停止。
- `daemon --restart --when-idle [--timeout S]`：默认最多等 300 秒，跨所有 Router 等待 temp 的 QUEUED/RUNNING/DISPATCHING 排空及超时原生回合结束；超时报告阻塞原因并保持原 daemon。最终检查、关闭新任务入口和停止共用调度锁，确认旧 daemon 释放实例锁后才启动替代进程。

通信格式、临时/正式会话的 token 取舍、Linux 沙箱定向出口和原生问答边界见 [通信与沙箱](../../../docs/communication-and-sandbox.md)。

## 回传与恢复

任务有独立 QUEUED / DISPATCHING / RUNNING / READY、BLOCKED / FAILED / INCONCLUSIVE / CANCELLED，以及 ACCEPTED / REJECTED。断连接或不确定派发不重放副作用，按真实 thread/turn 和结果恢复。超时标明需要检查，不误杀人的后一个回合。BLOCKED/INCONCLUSIVE 不代表原生 turn 已停止：仍活跃时继续占用写入位置并阻止空闲重启，直到完成或显式取消；晚到结果保存在原任务中，不自动改变验收状态。

Claude 的 PostToolUse/Stop asyncRewake hook 等待所属任务，结果需要处理时按原生协议退出 2 提醒 Router；没有任务时立即退出。暂停/人工控制时不自动唤回继续派活。一次提醒不会循环烧模型；未验收结果持续留在 inbox，恢复或下一次用户输入会再次显示。

协调状态在 `~/.local/state/claude-codex-workflow/`（0700，数据库/日志0600）。native chat 留在 Codex 存储；temp 不承诺跨协调进程恢复完整上下文。运行状态损坏要保留诊断，不当空库重建。实际已验证与尚待用户试点的边界以部署回执为准。

状态扩展保持 schema `1`：takeovers 为附加表，任务计时和 Worker pinned 为附加列，0.2.0/0.2.1 可继续打开；此前标为 `2` 的库在事务中归一为 `1`，不丢弃既有数据。升级前仍保留状态备份；旧版会忽略 pin 或 takeover 等新行为，回滚前先结束临时执行并处理活跃任务。

## 安装与生效

从本仓库源码 checkout 运行 `PYTHONPATH=src python3 -m claude_codex_workflow.cli install` 预览，追加 `--apply` 安装当前用户。Linux Router 端用 `--role both`；仅本地 Codex 维护端用 `--role worker`。安装器固定内容版本，合并自己的入口/hooks、保留 provider/隐私设置、备份并使用既有 agents-sync 源链。`git pull` 不自动升级安装版。

已运行的 daemon 不会自动加载新 release。安装回执的 `daemon_restart_needed` 和 `recommended_daemon_command` 会提示是否需要 `ai-work daemon --restart --when-idle --timeout 300`；随后用 `doctor` 核对运行 release 与 `current`，同版本号的不同内容也会被识别。尚不支持原子空闲重启的旧 daemon 会得到明确拒绝，不退回先查询再直接 stop；首次升级需 Router 协调所有使用者安排受控空窗。

本机 Codex 0.166.0 的隔离实验显示：ephemeral 在重连后虽可读取活跃摘要，但不能 resume、读取 turn 历史或重新接收完成结果，因此本实现仍保留 temp 的保守恢复策略，安全重启必须等待其排空。证据见[验证范围](../../../docs/runtime-validation.md#ephemeral-重连调查)。

短入口正文以 `rules/entries/` 为单一源；角色技能在 `skills/`，详尽指导在 `docs/`，程序只做适配与校验。参考文件在安装包中由同源文档生成并修正链接，不手工维护两份内容。

全局表示当前主机/当前用户的所有项目，不表示其他机器或其他 Linux 用户。技能只在相关任务加载。安装后先保存工作，再正常退出唯一的 Claude 进程，`claude --resume SESSION_ID` 恢复最稳妥；不要在两个 tmux 同时恢复同一 Claude 会话。部分技能/hooks可热加载，但旧上下文不因此自动清除旧规则。

旧 nested 会话保留。选一个作为 Router，恢复后明确按新规创建/复用 Codex Worker；不批量关闭、合并、重命名旧会话。回滚用 `uninstall` 先预览、再 `--apply`，仅在文件仍匹配安装后快照时恢复上次版本，后续改动存在则拒绝覆盖并要求合并。
