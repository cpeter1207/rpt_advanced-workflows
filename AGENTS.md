# rpt_advanced workflow development rules

## Shared rpt_advanced project baseline

This baseline applies to every production, shared-library, and workflow
repository in the rpt_advanced project. Repository-specific rules may add
constraints but must not weaken it.

Run platform-independent formatting, lint, static analysis—including
Cppcheck—and Doxygen once, concurrently where independent. Do not run Cppcheck
in each platform job. Run platform-dependent tests, coverage, build, packaging,
and staged-install checks concurrently across Debian 12 and 13 on native amd64
and arm64. Quality checks must not rewrite source files.

Complete the full quality gate before pushing, opening or updating a pull
request, merging, tagging, or releasing. Local recovery commits may follow
affected targeted checks, but must not be represented as fully verified or used
for a push, pull request, merge, tag, or release until the full gate passes.
Treat compiler warnings as errors and fail applicable formatting, Ruff,
ShellCheck, Cppcheck, Clang-Tidy, Doxygen, tests, installation checks, and 100%
line and branch coverage. Remove unreachable or dead code instead of
suppressing diagnostics or excluding it from coverage.

Update concise Doxygen comments, tests, user documentation, examples, and
build, install, and package artifacts whenever an interface changes. Consumers
of a shared project library must use its released, versioned dynamic shared
object rather than vendor or statically link a duplicate implementation.
Preserve published ABI/API compatibility whenever practical; when a change is
necessary, document its compatibility, SONAME/package consequences, and
migration. Start and clean only project-owned, labeled test containers
deterministically. Never deploy to a node or alter its configuration without
explicit approval.

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
