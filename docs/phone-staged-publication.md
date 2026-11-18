# Isolated staged qualification publication plan

Preparation only. No source, workflow, image, release or APT publication has
occurred as part of this patch. The earlier manual-only invocation limitation
is superseded by one exact qualification-branch push trigger.

## Proposed source publication, first

- Repository: `cpeter1207/rpt_advanced`
- New ref: `refs/heads/qualification/phone-staged-20261118`
- Commit: `bc46f631d8da28fd69b41e4e1c33c7e3410d163b`
- The remote currently exposes old qualification source `5e94f7d`; the public
  commit lookup for `bc46f631` returned HTTP 422. Verify the exact new remote
  ref before publishing the workflow. Do not update the old qualification ref,
  main, tags, releases, packages or node state. Ordinary controller push checks
  may run; this is not a deployment.

## Proposed workflow publication, second

- Repository: `cpeter1207/rpt_advanced-workflows`
- New ref: `refs/heads/qualification/phone-staged-20261118`
- Commit: the separately reviewed trigger/image-pin commit containing this file.
- The new ref was absent at preparation time. Check absence again; do not force
  over an unexpected existing ref.
- Push matches only `phone-staged.yml`. Old `phone-cohort.yml` matches only
  `qualification/phone-downlink-20261117`; validation push matches main; all
  other workflows are call/dispatch-only. A regression checks this isolation.
- The workflow has read-only repository permissions, no tag/latest push,
  release/APT operation, or live-node operation. Private diagnostic artifacts
  include packages that remain unqualified until every required gate succeeds.

## Immutable image evidence

Index:
`ghcr.io/cpeter1207/rpt-advanced-quality-debian13@sha256:c3800ed0094d0d01284b70481d3189a76044042b2900594115db2e2a41f2d0fa`

Registry metadata was retrieved without pulling layers. Native manifests:

- amd64: `sha256:039255d13e2625f3abfc1766e2adb9cb0d8dfe1d38f4673557fc2ac89c725011`
- arm64: `sha256:3ff6153d99b045d9a5a067d84fdcd346e2faf88b6c8c50bc59696faabf9bbeb9`

Config image IDs:

- amd64: `sha256:d6acd42a4bcb1138e8ea5a9524b1b9f04ee39b6102d41183c8820d9aa4300b12`
- arm64: `sha256:f877edda4e454a67ca6f521c1b3f31780115941ad8cfe5ba84d264e9d7de5be7`

The workflow resolves and verifies these architecture-specific selections at
run time from the pinned index, retaining receipts with the executed workflow
SHA. This does not claim runtime-container inspection that was not performed.

## Validation and remaining gates

The trigger patch passed 116 Python discovery tests, scoped Ruff, and diff
checks in the capped, offline cached amd64 image. All staged inline shell
programs are unchanged from the 25-program ShellCheck-passed baseline.
Actionlint is not installed locally. The repository's existing
`raven-actions/actionlint@v2` check is now required in the metadata job, before
package preparation. Its hosted execution is still pending, not reported green.

Review and applicable publication approval remain required. Native preparation,
Sofia upstream tests, full ordinary gates, installed runtime tests and coverage
remain unrun. First hosted runtime is unmeasured; do not promise hardware-ready
artifacts from fast validation alone.
