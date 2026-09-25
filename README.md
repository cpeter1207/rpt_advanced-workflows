# rpt_advanced-workflows

Workflow implementation repository for
[rpt_advanced](https://github.com/cpeter1207/rpt_advanced).

The project's [platform and quality requirements](https://github.com/cpeter1207/rpt_advanced/blob/main/QUALITY.md)
are maintained in the production repository. Workflow implementations belong
here; production code does not.

Production callers follow `main`. A production push calls the reusable
preflight, which runs only formatting, lint, and static analysis. A pull request
calls the reusable full quality gate: shared checks followed by native-platform
test jobs and a parallel amd64 coverage job. Workflow-only updates do not start
production builds. Workflow validation runs independently on pull requests.

The manually dispatched **Publish quality images** workflow builds Debian 13
images on native amd64/arm64 runners. It provides the current Rust toolchain,
FFmpeg, libclang, and released `rate_adjusting_pcm_ring` and
`rptadv-samplerate-adapter` development packages. The `latest` manifest is
updated only after both native builds pass. These are quality images, not
clean-install or installed-release images.

**Publish verified ASL3 test images** resolves a production ref to one commit
and builds clean ASL3 and installed-package images for Debian 13. It deliberately
does not repeat the pull-request quality gate. The installed image runs the
production repository's isolated Asterisk tests against the Debian package; the
test driver is never part of the package installation files. Debian 13 gets
`rpt-advanced-test-asl3-debian13` and
`rpt-advanced-test-installed-debian13` manifests tagged with the tested commit
and `latest`. Publication waits for every native-platform build and smoke test.
The workflow also supports `workflow_call` with `code_ref` so release automation
can reuse it for the exact release revision. No workflow-only push starts it.

The reusable **Verified source release** workflow accepts version-tag callers.
It requires the tagged main commit to be the merged result of a pull request,
requires its source tree to match that pull request's successful full quality
gate, then runs artifact-specific image publication and Debian package builds.
It does not repeat the full gate. Both images, Debian 13 amd64/arm64 packages,
and the source archive use the caller's exact commit. Tags with a suffix are
GitHub prereleases. Creating or editing workflow code does not create a release;
the production repository must push a version tag through its thin caller.

After a validated change reaches `main`, the thin documentation caller rebuilds
and publishes that revision's Doxygen and Rustdoc sites. Documentation
validation remains part of the pull-request gate; publication is intentionally
separate from the fast push preflight and releases.

The production repository's branch protection requires pull requests, linear
history, resolved review conversations, and the full `Required quality / Required
quality gate` pull-request check; it prohibits force pushes and branch deletion.
This workflow repository requires only its independent `validate` check, so a
workflow repair never depends on the production workflow it repairs.

## Local production-workspace containers

`tools/run-in-quality-container.sh IMAGE WORKSPACE COMMAND [ARG...]` runs an
explicit production workspace in a freshly pulled labeled quality container.
It reports the image digest, removes only stopped containers matching that
workspace, and removes its own container on exit. For example:

```sh
tools/run-in-quality-container.sh \
  ghcr.io/cpeter1207/rpt-advanced-quality-debian13:latest \
  /path/to/rpt_advanced make rust-coverage
```
