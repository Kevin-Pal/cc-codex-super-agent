# Execution, access and platform boundaries

The collaboration rules are platform-neutral. The intended runtime targets macOS/Linux POSIX environments; universal OS compatibility is not established.

| Layer | Portable project responsibility | Instance detail |
| --- | --- | --- |
| Rules and templates | Roles, task authority, evidence and continuity | Personal preferences and project memories |
| Runtime | Coordinator, state, native adapter, hooks and versioned installation | Interpreter paths and process management |
| IPC | Chosen local transport and lifecycle checks | Socket locations and permissions |
| Access | Document native Desktop/SSH usage | SSH aliases and local connection settings |
| Provider/privacy | Preserve external configuration; optional adapters | API providers, auth, telemetry choices and sandbox exceptions |

Unix sockets are a runtime implementation choice, not inherently a personal customization; both macOS and Linux provide them. The working mainline also uses POSIX file locks/process behavior. Specific socket paths and a host's sandbox policy must be discovered/configured per instance. No Windows-native runtime support is claimed.

Working-mainline experience: Linux execution plus Mac native remote access was exercised end to end; Mac runtime tests and optional Worker-rule installation were checked. A complete Mac Claude Router plus local native Codex plus real hook-wakeup acceptance remains a future gate. These observations are not a runtime validation result for this candidate, whose runtime is not imported.

Before claiming macOS/Linux support in a release, validate both execution platforms, install/rollback, native endpoints, temporary paths, notifications and optional sandbox compatibility. The separate access host uses native behavior and does not inherit the execution host's privacy/provider settings.
