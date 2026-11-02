# 规则源

本目录维护 V2.0 规则。长版角色规则用于审查语义与专项参考；`entries/` 是安装器实际读取的短入口单一源，不在 Python 代码里维护另一份正文。

- [shared.md](shared.md)：共同目标、授权与证据。
- [claude-router.md](claude-router.md)：理解、设计、派活、验收和最终交付。
- [codex-worker.md](codex-worker.md)：被委派执行与用户直接维护的区别。

当前方向以 [设计决策](../docs/design-decisions.md) 为入口：临时/正式/个人三类会话、持续复用与人工交流、共同项目知识、按需技能，以及原有轻量路径与 hard 默认。安装器合并自己的共享/角色标记块，不能直接替换整个用户全局文件。

安装时按 [分层加载设计](../docs/instruction-delivery.md) 使用 `entries/` 短常驻入口、角色 skill 与专项参考，不把长版全部注入每轮。修改规则源后经审查安装并验证；只 Git pull 不会覆盖现场。当前源码包含首版运行实现，见 [实际验证](../docs/runtime-validation.md)。
