# Independent review draft

- Requirement and invariants: <what must be true>
- Review target: <immutable commit/snapshot and allowed paths>
- Evidence: <original inputs, commands and outputs>
- Review capabilities: <read-only, authorized research if needed>
- Independence: new session; no implementation memory when supported and verified
- Output: findings with evidence, severity and a reproducible check; PASS / FAIL / INCONCLUSIVE

First judge the requirements and evidence independently, then compare the implementer's explanation. Do not change tests or code to make a verdict pass. Lack of evidence is not proof of correctness.
