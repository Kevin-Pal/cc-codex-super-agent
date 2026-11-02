# Independent review draft

- Acceptance tier: <L2 code review | L3 deep cross-verification>; user-specified focus: <if any>
- Requirement and invariants: <what must be true>
- Review target: <immutable commit/snapshot and allowed paths>
- Evidence: <original inputs, commands and outputs>
- Review capabilities: <read-only, authorized research if needed>
- Independence: new session; no implementation memory when supported and verified
- Output: a short structured list the Router can act on without rereading everything: each finding with severity (P1/P2/P3), file:line or artifact, evidence and a reproducible check; then PASS / FAIL / INCONCLUSIVE and what was not checked

First judge the requirements and evidence independently, then compare the implementer's explanation. Do not change tests or code to make a verdict pass. Lack of evidence is not proof of correctness.
