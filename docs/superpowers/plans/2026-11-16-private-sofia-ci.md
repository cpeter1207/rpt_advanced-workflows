# Private Sofia CI Provisioning Implementation Plan

**Goal:** Supply exact Sofia1.13.19 to existing CI checks without publishing a combined image or dependency package.
**Architecture:** A composite action runs one pinned source-build helper into RUNNER_TEMP, verifies the dynamic installation, and exports both Make and Cargo prefixes. Existing checks remain unchanged. Production callers continue to follow workflow main.
**Constraints:** Archive SHA25699389b574dfcff5775b260dd9ef1bdd2bcb5a42e655bd229d477e488e658064f; upstream6dce59d35535e6dd3945c7b0f76dbf1ba884202d; upstream-default features, dynamic-only; bounded serial build. No node use, image publication, dependency dummy packages or packaging bypass. Distribution/license hold remains. Package gates still require a real qualified Sofia development package.

- [ ] Test real hash rejection, missing/wrong install metadata, environment exports and workflow wiring before implementation.
- [ ] Implement tools/provision_private_sofia.py and .github/actions/provision-private-sofia/action.yml; wire preflight and quality jobs.
- [ ] Run workflow suite, Ruff, ShellCheck/actionlint where available and fresh pinned build in constrained container; verify header/linking and controller C check.
- [ ] Independent review; no push before applicable checks/review.

Review focus: private path containment; archive integrity before extraction/build; exact version and dynamic SONAME; Make/Cargo prefix consistency; no artifact publication or packaging dependency bypass.
