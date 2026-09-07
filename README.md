# rpt_advanced-workflows

Workflow implementation repository for
[rpt_advanced](https://github.com/cpeter1207/rpt_advanced).

The project's [platform and quality requirements](https://github.com/cpeter1207/rpt_advanced/blob/main/QUALITY.md)
are maintained in the production repository. Workflow implementations belong
here; production code does not.

Production callers follow `main`. The reusable quality workflow runs shared
checks followed by four native-platform test jobs. Workflow-only updates do not
start production builds. Workflow validation runs independently on pull requests.

The manually dispatched **Publish quality images** workflow builds Debian 12/13
images on native amd64/arm64 runners. It adds the FFmpeg executable to the existing
ASL3 quality environment and verifies tools before publishing architecture tags.
The `latest` manifests are updated only after all four builds pass. These are
quality images, not clean-install or installed-release images. The quality
workflow consumes `ghcr.io/cpeter1207/rpt-advanced-quality-debian12:latest` and
`ghcr.io/cpeter1207/rpt-advanced-quality-debian13:latest`; both manifests have
verified public amd64 and arm64 images.

**Publish verified ASL3 test images** resolves a production ref to one commit,
runs the same required quality gate, and builds clean ASL3 and installed-module
images. The installed image runs the production repository's isolated Asterisk
audio tests; the test driver is never part of the module's installation files.
Each Debian version gets `rpt-advanced-asl3-debianN` and
`rpt-advanced-installed-debianN` manifests tagged with the tested commit and
`latest`. Publication waits for every native-platform build and smoke test.
The workflow also supports `workflow_call` with `code_ref` so release automation
can reuse it for the exact release revision. No workflow-only push starts it.

Branch protection requires pull requests, linear history, and resolved review
conversations, and prohibits force pushes and branch deletion. No nonexistent
status checks are required; the existing `validate` check is required. Workflow validation remains independent of
production tests so broken workflows can be repaired.
