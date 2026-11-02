# 额度暂不可用时的独立工作与恢复

用户已确认的目标：任一方额度暂时耗尽，可以由另一方独立工作；恢复后再协调同步。Router/Worker 是正常情况下的分工，不要求两者始终同时可用，也不把人的两个直接入口封死。

## 双向接管约定

| 暂时不可用的一方 | 另一方如何工作 | 保留什么 |
| --- | --- | --- |
| Claude Router | 已在执行的 Codex 继续已授权任务；人可以直接与正式 Worker 交流或在 Codex 自建 session 中工作 | 原 thread/工作线、人工新决定、共享项目文档、产物与待验收结果 |
| Codex Worker | 人可明确让 Claude 暂时承担实质执行，而不只限于原本的微任务；先界定本次工作与写入范围，处理旧 Worker/队列状态 | 已完成的工作、真实检查、未决假设、人工/Claude 直接变更，以及恢复后需要独立复核的项 |
| 两边都不可用 | 人仍可查看已有项目文件、聊天与已保存结果，手动处理或等待 | 当前状态、暂停/取消标记、待续工作；不凭空新增模型能力 |

切换时仍核对是否有回合或远端作业正在运行。达到额度、调用报错或失去响应，不足以证明原执行已经停止；先查真实状态，避免两份写入或重复副作用。需要人指挥的另一入口本来就存在，不必为了临时可用性迁移账号、复制聊天或创建一套新项目记忆。

Claude 临时执行时，明确记为它完成的直接工作，不伪造 Codex turn 或 Worker 验收记录。共享项目知识记录变更、证据和未决事项；较重要的改动可在 Codex 恢复后补独立复核。

## 恢复后先同步，再回到默认分工

1. 获取双方新的对话输入、决定、产物、Git 差异及相关未提交变化；不能只读恢复前缓存的工作包。
2. 更新同一套项目权威文档，区分已验证结果、临时判断与待审工作。
3. 核对 stream/thread/task 的对应关系及实际活跃回合。旧队列已不适用时修订或废止，不直接重放；持续 Worker 优先续用原 thread。
4. 由人或负责的 Router 明确当前控制权和下一步，再回到通常的 Claude 调度/Codex 执行。额度恢复本身不解除用户的暂停、接管或取消。

## 0.2.1 的显式临时执行

此入口的实现不以检测额度为前提。0.2.2 同时明确用于用户点名 Claude 的优化、设计与实质写入，见 [Claude 亲自工作](claude-direct-work.md)；这里的额度场景只是用途之一。

现有直接 Codex 入口、原生持续 thread、共享项目文件、持久结果、人工控制和同步校验，为这套恢复约定提供基础。Claude 不可用时，人可直接与 Codex 工作，恢复后 Router 同步。

用户明确授权 Claude 临时执行后，使用 `ai-work takeover --router ROUTER_ID --scope /absolute/project --reason "Codex quota temporarily unavailable"`。`--scope` 可重复，目录包含其子路径，文件按精确路径授权；路径按组件匹配并解析符号链接。`--hours` 默认 2，允许大于 0、最多 8 小时，到期自动失效。原来的 `direct` 单文件微任务例外仍独立保留。

`ai-work takeover --router ROUTER_ID --status` 查看范围与剩余时间；结束前将变更、证据和待复核项写进共享项目文档，再用 `ai-work takeover --router ROUTER_ID --release --note "Evidence recorded in shared docs"` 结束该 Router 的全部有效 takeover。开始、释放和到期均持久记录为 Router direct work；到期结束事件在下一次状态读取时补记。

同工作树已有 RUNNING/DISPATCHING 写入任务，或本 Router 的重叠 Worker 处于 manual 控制时拒绝申请，提示先取消/同步或由人确认控制权；其他 Router 的有效 takeover 也不能重叠。有效期间阻止同工作树写入 Worker 的新派发和旧队列启动，独立只读审核仍可运行。不会自动取消原生回合或解除人的 manual/paused 状态。

UserPromptSubmit 显示有效范围、剩余时间和共享文档提醒。恢复后先 `sync`：重叠路径或同工作树的 takeover 事件会进入同步结果和 token，并在后续 Worker 派发提示中明确标为 Router direct work；旧 token/旧队列需要刷新或修订，不伪造 Codex turn 或验收。重要变更可另派独立复核。

0.2.1 源码已实现上述显式入口；安装与真实会话验收仍以实例回执为准。没有自动额度检测、自动角色互换或自动重派，也不自动开付费超额、升级套餐或切换供应商。
