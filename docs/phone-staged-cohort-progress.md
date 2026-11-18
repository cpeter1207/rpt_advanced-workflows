# Staged cohort implementation checkpoint

This is incomplete workflow preparation, not qualification or a deployable image.
Design review was reported clear by the coordinator before implementation.

Implemented through 57552d1:

* Separate exact staged manifest for controller bc46f631; five provider pins
  unchanged; original phone-downlink manifest untouched.
* Pinned baseline candidate installer 0fd80670536df45efb5b9738e6c116f1f9527870.
* Guarded native-CI-only private provider package preparation with same-version
  replacement, source checks, archive/installed-header/ELF hashes and loader
  dependency resolution. No preparation command has been executed.
* Direct compiled test-binary launcher, not cargo-as-launcher, with installed
  provider paths and actual glibc loader traces. Original 52 assertions retained:
  5 downlink, 2 SIP, 37 ordinary native RTP plus 1 recovery-fixture case, 7 rings.
  The recovery case has seven deliberate fault-shim child modes; only its exact
  parent-owned temporary shim path is separated from package-byte proof. The
  real provider must still be observed and match selected package bytes.

Local verification: 17 staged identity tests, 6 package-plan tests, 5 installed
launcher tests and 12 existing cohort tests pass (40 total). Tests use temporary
files; one builds/extracts a tiny header-only test .deb without installing it.
No production compile, container, package installation or publication occurred.
Whitespace checks pass. Full Python discovery earlier ran 79 tests with 74
passing and 5 missing-tool errors: ShellCheck in private Sofia/action-shell,
radio/action-shell and radio/image-shell tests; pkg-config in wrong-Sofia-version
case; C compiler in SDK-mixed-header probe. Do not call the full suite green.
Ruff/actionlint validation is still pending in a tool-complete environment.

Remaining implementation: artifact consumption/full native gate runner; manual
workflow and image digest/job wiring; additional runner behavior tests and
independent review. No new workflow trigger has been added.

Confirmed prerequisite: controller Debian Build-Depends requires
libsofia-sip-ua-dev >=1.13.19 and SIP runtime Depends requires libsofia-sip-ua0
>=1.13.19. Existing private Sofia provisioning supplies a temporary dynamic
prefix, not those Debian packages, and explicitly does not claim distribution
qualification. A real provenance-verified package pair is required for ordinary
package/install success. Never use -d, equivs, fake versions or merely the
private-prefix library to attest that dependency. The private test launcher
retains only the exact validated pinned Sofia prefix, separately recorded.

RNNoise platform-verify includes Docker autopkgtest; its native pinned testbed
must be supported, not omitted or mistaken for a plain in-container unit test.
No main, release, APT, registry image, IAX source, or running-node changes.

## Recovered implementation checkpoint: ordinary gates and hosted testbed

The gate runner now restores the exact prepared archive inventory, binds it to
workflow/source/architecture/image/baseline identity, and verifies installed
header and ELF hashes before running the existing ordinary target plans.
Native controller packages are installed before the 52-selection installed
binary test runner. Command logs survive failures; timed-out gate process groups
are stopped. Independent checks remain once on amd64, native checks on both
architectures, and production coverage amd64 only.

The new RNNoise helper reuses the pinned provider's Dockerfile, requires a native
GitHub-hosted runner with disk reserve, supplies an immutable quality base,
records recipe/base/local image identity, and never tags or pushes. The native
gate validates this receipt before passing the exact local image ID to the
provider's existing autopkgtest target. The source Dockerfile still has its own
versioned Dockerfile frontend and apt/toolchain fetches; receipts identify the
resulting local image rather than claiming bit-reproducible network inputs.

Validation at this checkpoint: 55 focused tests passed (2 testbed, 3 Sofia,
9 gate contracts, 5 installed runner, 6 package plan, 18 identity, 12 original
cohort), plus git diff --check. No native package build, full ordinary gate,
container build, or installed test execution has occurred here. Existing full
workflow discovery is still nongreen because the host lacks ShellCheck,
pkg-config and a C compiler. Tool-complete lint/review and manual-only workflow
orchestration remain before a hosted invocation can be proposed. No publication
or live-node modification occurred.
