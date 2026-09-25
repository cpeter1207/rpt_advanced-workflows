# rpt_advanced workflow development rules

## Shared rpt_advanced project baseline

This baseline applies to every production, shared-library, and workflow
repository in the rpt_advanced project. Repository-specific rules may add
constraints but must not weaken it.

Run platform-independent formatting, lint, static analysis—including
Cppcheck—and Doxygen once, concurrently where independent. Do not run Cppcheck
in each platform job. Run platform-dependent build, tests, packaging, and
staged-install checks concurrently on native Debian 13 amd64 and arm64. Require
100% line and branch coverage of production code only on Debian 13 amd64; test
code is excluded from the coverage requirement. Debian 12 support is
aspirational: do not run automated Debian 12 tests or build Debian 12 packages
as part of ordinary pushes, pull requests, or releases. Build Debian 12
packages manually only when explicitly requested. Automated releases publish
Debian 13 packages only; node installations use Debian 13 arm64 packages.
Quality checks must not rewrite source files.

A production push runs only formatting, lint, and static analysis. It does not
run Doxygen, the platform matrix, coverage, packaging, or installation checks.
The complete quality gate, including those checks, must run on every pull
request and pass before it merges. A release relies on that successful merged
pull-request gate and validates only its release artifacts; it must not invoke
or repeat the complete quality gate. Treat compiler warnings as errors and fail
applicable formatting, Ruff, ShellCheck, Cppcheck, Clang-Tidy, Doxygen, tests,
installation checks, and 100% line and branch coverage of production code on
Debian 13 amd64 where the applicable workflow runs. Remove unreachable or dead
code instead of suppressing diagnostics or excluding it from coverage.

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

Run the full pull-request gate's platform-independent quality checks once,
concurrently where independent, before the Debian 13 amd64/arm64 test matrix
and Debian 13 amd64 production coverage. Run matrix jobs concurrently. The
push preflight contains only formatting, lint, and static analysis. A release
may validate its archives and installable artifacts but must not repeat the
full gate. Never claim a gate passed without running it.

Preserve the documented container, coverage, Doxygen, and installation-test
requirements. Clean up only project-owned test containers on start and exit.

Do not deploy to nodes or change their configuration without explicit approval.
Do not anticipate product requirements or add unrequested features.
