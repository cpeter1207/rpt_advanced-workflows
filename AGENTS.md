# rpt_advanced workflow development rules

Follow the production repository's
[QUALITY.md](https://github.com/cpeter1207/rpt_advanced/blob/main/QUALITY.md).

Keep workflow implementations here and production code in rpt_advanced.
Production callers follow this repository's main branch. Do not trigger a
production build/test cycle merely because a workflow implementation changes.

Validate workflow changes independently of production code. Do not make a
workflow repair depend on the production workflow it repairs passing first.
Enable required workflow-validation checks only when those checks exist.

Run platform-independent quality checks once, concurrently where independent,
before the Debian 12/13 amd64/arm64 test and coverage matrix. Run matrix jobs
concurrently. Pushes, pull requests, and releases must consume the same required
production quality gate. Never claim a gate passed without running it.

Preserve the documented container, coverage, Doxygen, and installation-test
requirements. Clean up only project-owned test containers on start and exit.

Do not deploy to nodes or change their configuration without explicit approval.
Do not anticipate product requirements or add unrequested features.
