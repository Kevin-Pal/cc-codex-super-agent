# 运行验证记录

## Public source snapshot 0.2.3.post1

公开导出增加安装保留性、既有生成链回滚、技能引用完整性、敏感文本检测及历史删除后仍可检出的回归。基础95项继续保留；公开快照在macOS Python3.13和Linux Python3.12各完整100项通过。新增公开安装器只更新自己的标记块/hooks，不清理个人旧标题、不覆盖其他包的codex-delegate入口。源码归档/新克隆安装均在隔离home验证，不改实际账户。没有为这次导出调用新的真实模型任务。


跨组件版本基线与升级复核见 [Harness 兼容记录](harness-compatibility.md)；历史功能验证按日期保留，不用今天的版本倒填。

## 2026-11-02 0.2.3 write admission

在 Claude 的 91 项基础上补四项：微任务期间取得的基线在到期后不能提交；期间已排队任务到期后 BLOCKED；重启 draining 时拒绝新 direct 窗口；无关项目的旧版队列凭据保持兼容。Mac 使用同一假原生端完整 95 项通过；首次沙箱内的真实 Unix socket 用例受限，沙箱外原样重跑通过。5060 Linux 隔离副本同样完整 95 项通过。未用真实模型来跑这些回归。

Desktop 专用 list_projects/list_threads 只读结果确认：现有 linked-worktree Worker 的应用层 Project 归属与原 checkout 相同，cwd 仍为 sibling worktree；原生 thread/list 的 projectId null 不能反推应用层分组。未取得目视截图；两个真实 Worker 的完整并行集成流程仍未验收。

旧技能删除与旧会话恢复分开看：Claude Code [官方技能生命周期](https://code.claude.com/docs/en/skills#skill-content-lifecycle) 说明 compact 会重新附上此前调用过的技能内容，删除文件不会移除已进入会话的指引。上下文 hook 对 retired codex-delegate 加当前入口提醒；这不是拦截原生恢复。不要为清理提示篡改聊天记录；可在旧会话明确废止旧指引、加载当前技能，必要时带共享项目状态新建会话。

## 2026-11-02 0.2.2 retention / explicit Claude work

Mac 与 Linux 的隔离回归各 80 项通过（含本轮新增 9 项）。覆盖：正式 Worker 验收后同 thread 复用；temp 在 priority limit 前排除；只检索所属登记且不加载原生历史；pin/unpin 不改变 manual/paused；released 保留记录且不自动恢复；hook 十项优先清单；用户明确指定 Claude 设计时，无需额度失败即可使用既有范围 takeover，范围外/释放后写入拒绝，变更进入 Worker 同步。

额外用上一版 0.2.1 的 Store 打开 0.2.2 附加 pinned 列的隔离状态库，原控制状态与 pin 保留；仅加列、schema 仍为 1。Mac 首次沙箱运行有一项临时 Unix socket 启动失败，获准在沙箱外用同一假原生端重跑后 80 项通过。技能结构和本地 Markdown 链接检查通过。没有为这些回归调用真实模型。

这些证据验证接口/规则入口与协调行为，不能证明语言模型一定按用户期待做设计或独立核验。新规则安装后的实际 Claude 决策，由用户常用 Router 下一轮确认；不得把假模型检查标成新的真实交互验收。后台 idle 扫描降频和 Desktop archive 联动未实现，不自动归档或重新接管已 released 会话。

2026-11-02。首版已实现，不是仅有规则草案。实例安装路径、私有原始结果、thread/task ID、SHA 与回滚不放在此通用仓库。

| 范围 | 已做的验证 |
| --- | --- |
| 原生控制通道 | 接入现有 Codex 0.166.0 Unix WebSocket control socket，使用同一运行时；未新开公网端口/复制认证/修改历史数据库 |
| 正式会话 | 三轮同 thread；协调客户端重建后取回状态与结果；Desktop 远端 history 能发现同一正式 Worker |
| 第二客户端 | 在同一 thread 修改合成检查点；旧同步位置被拒绝，队列中的过期任务被阻塞；刷新后使用新决定 |
| 临时任务 | 原生 ephemeral 完成返回结果、从通常和显式来源历史列表隐藏、协调层释放；另一次 trusted temp 用真实工具写读指定新测试文件，独立读回验证 |
| 状态与异常 | 20 项自动化测试覆盖幂等、过期知识/外部输入、增量读取、暂停、未知派发不重放、同工作树写入互斥、空结果不算成功、最终交付优先、temp 结果/通知、接管边界、微任务例外和安装/回滚 |
| 技能与安装 | 两个 skill 通过结构校验；隔离假 home 验证幂等、保留非本包 hooks/配置、后续修改阻止回滚。现场安装与 native CLI 配置检查另见实例回执 |
| Claude 回传 | 实现持久 inbox 与原生 asyncRewake command hooks，直接测试终态退出 2、抑制重复提醒与暂停。2026-11-02 在用户实际交互 CC（安装前已启动的会话，hooks 热加载）实测：正式 Worker 三轮派活与一次 easy temp 完成后，空闲的 Router 均被 PostToolUse:Bash asyncRewake 唤回（temp 完成 06:21:21、通知 06:21:23），随后 result/review 闭环完成。唤回依赖 Router 最近一次 Bash 调用挂起的 watch hook，长于 45 分钟的任务不会触发唤回，需靠下次输入或 inbox。 |

试点暴露并修复了旧外部历史被重复识别、临时任务释放后不应丢通知等问题。外部回合尚未真正终结时，过期任务保持阻塞而不是强行执行；这是需要 Router 刷新/修订的正常分支。

## Ephemeral 重连调查

2026-11-02，CLI 与原生后端均为 0.166.0（initialize 返回 Codex Desktop/0.166.0），本轮只使用新建的隔离 ephemeral thread：启动一个无文件写入的短回合，在 inProgress 时关闭客户端 A，再从新客户端 B 查询。

- `thread/read` 可返回 active 摘要；按[官方协议](https://learn.chatgpt.com/docs/app-server)，读取本身不重新订阅事件。
- `thread/resume` 返回 `no rollout found for thread id`；`thread/read(includeTurns=true)` 返回 `ephemeral threads do not support includeTurns`；`thread/turns/list` 返回 `ephemeral threads do not support thread/turns/list`。
- 重连后等待 45 秒未收到该回合的 `turn/completed` 或最终消息；清理时 interrupt 返回 `no active turn to interrupt`，unsubscribe 返回 `notSubscribed`，随后该 thread 已不在 loaded 状态。未操作其他 Router 的 Worker，也未重启协调或原生服务。

据此不宣称 temp 可以跨协调进程重连恢复结果；未知派发不重放。新回归覆盖运行/排队独立计时、超时后的原生写入占用、晚到结果、跨 Router 空闲检查、重启竞态/超时、假 daemon 的真实控制 socket 替换、release 比较、schema 1/2 兼容和 worktree 查询缓存。真实生产升级与 Claude 交互验收仍由实例试点完成。

## 实际限制

- 原生 control/socket 与协议仍随 Codex 版本变化；本首版针对上述安装版本验证。不可用时明确报错，不静默另起 runtime 或回到一次性 exec。
- guard 是角色纪律，不是 OS 隔离，也不能证明任意 Bash 都无法写文件。宽权限的授权边界仍需具体工作包和 Router 验收。
- 原生 UI 的所有手势、抢占竞态、多个未纳管个人 session 在同一工作树写入，不由 wrapper 锁绝对控制。已纳管任务互斥；人的工作仍需协调。
- 项目刷新覆盖共同入口、常见状态文档及入口链接到的本地 Markdown；非标准动态事实仍应由 agent 按任务读取并在索引中登记。
- 独立 reviewer 从干净 thread 开始并关闭原生 memories 使用/生成；验收数据应给不可变快照，不能把两个模型意见一致当作正确。
- 本轮没有性能/成本基准，不承诺节省比例；还需要日常任务反馈。GPU/大实验的资源约束应明确写进工作包，当前执行槽与写入互斥不等于 GPU 调度器。

后续 Claude 可在 [目标与手段边界](claude-review-handoff.md) 内优化，并重跑受影响用例。未来公开版本从经过隐私/来源审查的阶段性快照发布，当前不公开。
