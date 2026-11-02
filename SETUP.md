# Source installation

## Prerequisites

Use Python 3.11+ and Git on macOS/Linux. This snapshot uses POSIX locks and Unix sockets; native Windows is not validated. Keep the project entry directory, Claude CLI, native Codex backend and framework under one execution host/user. You need your own working access to both harnesses.

First make the native Codex Desktop/Remote connection work and open the target directory there. The tested backend exposes `~/.codex/app-server-control/app-server-control.sock` (or the corresponding CODEX_HOME path). Check the actual endpoint, not only `codex --version`. A standalone CLI installation or a new generic app-server process does not guarantee the shared control endpoint this adapter expects. Stop at an unavailable endpoint rather than starting a second runtime or falling back to one-shot exec.

## Preview, then install

From the repository root:

```sh
PYTHONPATH=src python3 -m claude_codex_workflow.cli install --role both
PYTHONPATH=src python3 -m claude_codex_workflow.cli install --role both --apply
```

The preview lists changed paths. Applying creates a versioned user-local bundle and `~/.local/bin/ai-work`, links the two role skills, merges owned global instruction blocks/hooks, and records private rollback snapshots. Ensure `~/.local/bin` is on PATH. It does not change provider/API/authentication/telemetry/sandbox fields or operate the native Codex service. Existing managed skill names owned by something else are not overwritten.

Existing `agents-sync` setups with the documented `.agents/global/shared.md` and `codex.md` source layout are integrated through owned blocks and the existing generator. Arbitrary generators are not automatically supported; edit their sources with their owner instead of overwriting generated files. The public installer has no personal legacy-heading cleanup or codex-delegate rewrite.

The normal execution host uses `--role both`. An actual Codex-only execution/maintenance user may choose `--role worker`; a computer merely using Desktop Remote needs no installation. Use a Git checkout or source archive, not pip/wheel installation in this snapshot: runtime guides and rules are part of the root source bundle.

Open a normal Claude Router in the project entry directory, name it, and read `/claude-codex-router`. For existing Claude processes save work and reload supported settings/skills or exit the single process and resume; do not concurrently resume the same Claude history. Resume does not erase historical skill instructions. Confirm old delegation recipes are explicitly retired if migrating your own setup.

Run:

```sh
ai-work doctor
```

Check the connected native backend, tier/model resolution and `daemon_current_matches`. The coordinator starts on demand; no model task is sent by doctor. If upgrading an already running coordinator, let active work finish and run the suggested `ai-work daemon --restart --when-idle --timeout 300`; do not force-stop an unknown or ephemeral turn.

## Sandbox and permissions

Some Linux Claude Bash sandboxes block the coordinator socket. Keep the sandbox and review a narrow instance-specific exception for standalone ai-work scheduling calls if needed; the installer does not enable exceptions. Do not combine an exempt call with pipes, && or substitutions. Management commands such as daemon restart may need a separately authorized unsandboxed standalone invocation. See [communication and sandbox](docs/communication-and-sandbox.md).

trusted-worker intentionally uses broad native permissions with approvalPolicy=never; it still needs a bounded work package and Router acceptance. independent-review is read-only. Hooks do not inspect arbitrary Bash writes or provide same-user OS isolation.

## Optional manual Pro advisor

The installed bundle includes consult-gpt-pro but the installer does not activate its skill links. To opt in, link the bundle's `current/skills/consult-gpt-pro` directory into the client skill directory you use, after checking that destination is unowned. The link target is under `~/.local/share/claude-codex-workflow/`. Keep the complete installed bundle so references resolve. The skill prepares a user-relayed web consultation only after explicit choice; it does not operate a browser/clipboard or guarantee pricing/allowances.

## Rollback

Run `ai-work uninstall` to preview restoration of the last owned installation, then add `--apply` to restore it. Later edits block automatic overwrite and must be reconciled. The native sessions and project data are not deleted. Do not restore an old state database over newer tasks just to roll back rules. Stop/restart the framework coordinator only through its safe idle protocol when appropriate.

Source updates do not automatically update installed bundles. Read [operations](docs/runtime-operations.md), [compatibility](docs/harness-compatibility.md) and [validation](docs/runtime-validation.md) before upgrading.
