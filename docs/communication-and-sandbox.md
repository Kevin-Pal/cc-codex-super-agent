# 通信、Token 与 Router 的工具边界

源码快照 0.2.3.post1。当前行为说明；结构化问答桥仍未实现。

## 已有的原生适配

Claude 通过 `ai-work` 提交工作包、同步和读取结果；CLI 输出 JSON，经私有协调 socket 连接 daemon，再通过 Unix WebSocket JSON-RPC 接入既有 Codex App Server。原生接口提供 thread/turn 生命周期和完成事件，不依赖终端截图或模拟键盘。见 [OpenAI 官方协议](https://learn.chatgpt.com/docs/app-server)。

- 工作内容主要是文本提示与文本交付；thread/task/turn ID、状态、同步位置和事件是结构化数据。
- `result` 优先选 final_answer，附任务状态/错误及记录；当前返回整个任务记录，也包括原工作包，不是只返回最后一句。
- `sync` 增量返回输入与 agentMessage，可能含公开进度消息；有字符预算，不默认搬整段历史。reasoning 与工具输出事件不交给 Router 模型。排障/验收仍按需检查真实文件、差异和测试证据。
- daemon 等待、排队及 hooks 本身不调用 Claude 模型。自动唤回后的验收需要模型；不要让 Router 反复轮询或读取完整历史。

## 临时与正式 Worker

两者共用同一执行器、调度槽和模型档位选择。temp 是原生 ephemeral，主要减少日常列表污染、控制生命周期，不自带 Claude token 折扣；本版本还关闭 temp 的原生 memories 使用/生成。

一次性独立任务适合 temp；同一方向反复工作适合正式 Worker，可以少重复交代背景。正式会话历史也会消耗 Codex 上下文，temp 则可能需要重发背景，因此不能用会话类别直接推算总成本。当前没有成本基准或节省比例。

## Linux 沙箱兼容

保留 Claude Bash 沙箱和文件隐私限制，让可信调度工具有定向出口。具体例外由实例管理员审核、备份和安装，不在通用安装器默认开启。

[Claude 官方参考](https://code.claude.com/docs/en/settings-reference#sandboxnetworkallowunixsockets)说明 `allowUnixSockets` 按路径放行只支持 macOS；Linux 忽略该列表。`allowAllUnixSockets` 会开放所有 Unix socket，不能当成单个调度 socket 的白名单。

可以在当前用户的 settings 中使用 `sandbox.excludedCommands`，仅匹配已安装的 ai-work 调度子命令。例如使用真实、可信的绝对安装路径，分别加入 `.../ai-work doctor`、`.../ai-work sync *` 等；仅输入 `ai-work` 不等于匹配带参数的命令。保留其他既有例外，不豁免整个 Python、shell 或所有命令。完整匹配与混合命令规则见 [官方沙箱文档](https://code.claude.com/docs/en/sandboxing#run-commands-outside-the-sandbox-with-excludedcommands)。

被豁免的调用完全在 Bash 沙箱外运行，不是仍受文件隔离的 socket 连接。信任范围因此包含 ai-work、其运行代码、参数与读取的工作包文件；`send --file` 也会读取指定文件。代码被修改、解释器/导入环境被替换时不能声称仍有同等边界。应通过真实 CLI 离线测试确认调度成功、普通与混合 Bash 仍受限，并核对 provider 生成器是否保留非 provider 设置。

Bash 沙箱不隔离 Claude 主进程；它不保证设备匿名、登录风险降低或服务端不识别设备。受信任的高权限 Worker 也可能按指令读取信息，不能把 Router/Worker 分工当成不可绕过的保密隔离。工作包应限制无关私人数据进入回复。

## 提问与审批：下一版可选项

当前 trusted-worker 使用 danger-full-access 与 approvalPolicy=never，操作权限不等于任务授权。原生协议具有服务端请求/回复能力，但当前适配对未支持的交互请求返回明确错误，并未转成 Router 的待答队列。不能宣称此时一定会在 Desktop 留下待批准的问题。

人可以在 Desktop 的正式 Worker 中直接补充指令/纠偏，Router 跟进前刷新同一 thread。共享视图让双方看见同一历史，不能单独保证并发互斥；活跃回合、同步 token、队列失效和人工接管仍需要检查。对已识别的重大人工接管，保持 manual/paused，明确交还后继续。

用户已确认本轮不扩建问答桥。后续可先将问题/所需权限变成结构化待处理事件，Router 解决授权内的意图澄清，需要时向人提问；高权限审批保留人工决定。实现需处理请求归属、有效期、重复答复、多客户端抢答、断连及原生回合状态，不能只转发一句问题文本。

## 后续开发者的优化入口

- 为 result 增加可选紧凑视图，减少原工作包的重复回显；保留可取回完整证据的路径。当前尚未实现该选项。
- 结构化 artifact/test/evidence 清单、按需日志切片与 sync 分页/预算，避免把“少传文字”变成“缺乏验收材料”。
- 记录脱敏后的传输字符量、重复消息、唤回延迟和可取得的真实用量，区分 Router、Worker、缓存与重试成本，再评价节省。
- 原生交互请求变成有归属/有效期的待答事件，并处理多客户端抢答、断连和人工接管；高权限决定不能从一次自然语言回复推断。

这些是设计空间，不是当前已测得的性能优势。后端传输减少了终端搬运与状态猜测，但原生协议/实验字段、内容完整性和恢复仍需按版本验证。
