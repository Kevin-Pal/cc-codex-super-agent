# Contributing

Use synthetic examples and a bounded task; keep independent review and evidence proportional to the change. Preserve the Router/Worker contract, human control and one project authority.

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
python3 tools/sync_skill_references.py --check
python3 tools/check_publication.py --history
```

An optional repository-local pre-push hook can be installed with `python3 tools/install_dev_hooks.py`. It runs the publication check and does not change global Git settings or the private development repository. Hooks can be bypassed and are not server-side enforcement; review every outgoing change and commit identity regardless.

Keep auth/provider files, private logs, real task data, hostnames/home paths and personal memories outside this repository. Do not merge private repository history into a public branch. Export reviewed allowlisted files and retain exact provenance privately. See [snapshot policy](docs/snapshot-workflow.md).

Canonical guides live in docs/. `tools/sync_skill_references.py` materializes the mapped skill references; edit canonical guides and regenerate rather than diverging copies. Separate implemented behavior from proposals. Add a dated compatibility observation when an integration boundary changes.

Runtime bugs found here should be reconciled with any maintained development line before its next snapshot. Distribution-only changes must be recorded explicitly. Do not create tags/releases, upload packages, change visibility or add publication automation without an explicit maintainer decision.
