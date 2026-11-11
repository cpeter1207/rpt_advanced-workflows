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
FFmpeg, libclang, and SpeexDSP runtime and development files. Debian's
`sip-tester` supplies independent SIPp protocol scenarios; both native image smoke
tests execute its version command, which conventionally exits 99. This is a test
prerequisite. The image also installs pinned ring, samplerate, PortAudio/ALSA,
and FFmpeg development packages from
the production dependency manifest, plus released radio-core, GPIO, IAX2, and
nine functional-provider packages. Radio uses ABI 5
from v0.1.0-alpha.10; squelch and CTCSS use ABI 2 from v0.1.0-alpha.2, while
DCS, signaling, tone, Morse, DTMF, template, and schedule remain ABI 1. The
radio product runtime and development
packages (`libusbradioplus-product1` and `libusbradioplus-product-dev`) and their
RNNoise runtime dependencies come from USBRadioPlus's existing signed Debian 13
APT repository. Downloads use an isolated source/list directory and the
established signing-key fingerprint; they do not change the runner's APT sources
or install the USBRadioPlus Asterisk integration. The image verifies the product
header, native request ABI 4, pkg-config ABI 1, and `libusbradioplus_product.so.1`.
It requires USBRadioPlus alpha33 or newer and checks the installed runtime's
complete configuration, maintenance, update, observation and processing
descriptor tail without opening hardware. Owner/provider pkg-config metadata
and SONAMEs are also checked. The `latest` manifest is
updated only after both native builds pass. These are quality images, not
clean-install or installed-release images.

Normal RPT compilation uses pinned Rust 1.88.0; branch coverage uses
`nightly-2025-06-24`. These LLVM backends compile the SIP stack's optimized
atomic trait-object slot, which fails instruction selection with the previous
compilers. Each native image builds a reduced regression with both compilers
at optimization level 3, including branch instrumentation on nightly. Genuine
Debian Rust/Cargo packages from signed `trixie-backports` satisfy RPT's 1.88
build-dependency floor. Only compiler and standard-library packages receive the
backports preference; normal compilation still uses the pinned Rustup toolchain.
Other shared providers keep their own compiler requirements.

Dependency APT requests revalidation of cached HTTP/HTTPS metadata to avoid
pairing a stale cached release with a newer index during a package-site update.
The isolated source/list directory, pinned signing key, index hashes and SDK version floor
remain enforced. A native local-repository test reproduces the stale-index
failure and verifies revalidation without disabling hash checks.

When a dependency manifest selects EchoLink, the same signed repository supplies
the released jitter runtime in `dependencies/packages/bootstrap/`. Candidate
build containers install that prerequisite before building EchoLink. The returned
package set also contains the runtime for clean images; installed-source images
reinstall their own freshly built packages over any same-version prerequisite.

The functional-library extraction requires all nine providers and updated
radio/GPIO owner releases, followed by refreshed USBRadioPlus consumer packages
in the signed repository, before these dependency pins are merged and both
native quality images are refreshed. Only then can hosted rpt_advanced checks
and package builds consume the new boundary. Local candidate packages do not
satisfy this release/image-refresh prerequisite.

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
Package builds reinstall the shared dependencies selected by that production
revision before compiling, so the quality image cannot supply a stale SDK.
It does not repeat the full gate. Both images, Debian 13 amd64/arm64 packages,
and the source archive use the caller's exact commit. Tags with a suffix are
GitHub prereleases. Creating or editing workflow code does not create a release;
the production repository must push a version tag through its thin caller.

After a validated change reaches `main`, the thin documentation caller rebuilds
and publishes that revision's Doxygen and Rustdoc sites. It installs the released
shared dependencies selected by that checkout before generating documentation,
so a quality image's older SDK cannot supply the build headers. Documentation
validation remains part of the pull-request gate; publication is intentionally
separate from the fast push preflight and releases.

The production repository's branch protection requires pull requests, linear
history, resolved review conversations, and the full `Required quality / Required
quality gate` pull-request check; it prohibits force pushes and branch deletion.
This workflow repository requires only its independent `validate` check, so a
workflow repair never depends on the production workflow it repairs.

The **Focused Rust verification** dispatch accepts `check=integration` with an
exact production commit. After installing that revision's candidate dependencies,
it runs the existing `make integration` target, including the real Asterisk
lifecycle fixture, without coverage. The workflow unsets its SDK override for
that command so the production Makefile must select the source-built SDK itself.
This targeted check does not replace the complete pull-request gate.

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

### Constrained shared hosts

Set `RPTADV_CONTAINER_PROFILE=constrained` for local runs on a small shared host.
The launcher enforces one CPU, 1536 MiB RAM, no container swap, 256 tasks,
single Cargo build/test/OpenMP/BLAS concurrency, serial Make defaults, one active
constrained run per host account, and a 20-minute command deadline (TERM, then
KILL after 15 seconds). It still pulls
latest, records the digest and cleans only its own labeled containers. Passing
the host Docker socket or disabling the fresh pull is rejected in this profile.
Quality and clean/installed test images default Cargo builds, Rust tests, OpenMP
and BLAS to one worker. Docker resource bounds still require the constrained
launcher profile; image metadata alone cannot impose cgroup limits. The default
launcher profile and required hosted quality checks remain unchanged.

Only the constrained launcher sets glibc's `MALLOC_MMAP_THRESHOLD_=131072`
and `MALLOC_TRIM_THRESHOLD_=131072`. Fixed 128 KiB thresholds let freed large
allocations return to the OS rather than retaining a large high-water mark
between sequential stress tests. These are allocator reclamation settings, not
a reduction in test workload or a replacement for the memory limit. They are
not image-wide defaults and do not change production services. Non-glibc
allocators may ignore these settings.

Resource exhaustion or timeout is a failed run, never a skipped or passed test.
Do not increase these bounds on a shared production host without checking its
headroom. Some large stress tests may require a dedicated larger runner. This
profile does not replace the full native amd64/arm64 gate or coverage.

```sh
RPTADV_CONTAINER_PROFILE=constrained tools/run-in-quality-container.sh \
  ghcr.io/cpeter1207/rpt-advanced-quality-debian13:latest \
  /path/to/rpt_advanced make rust-check
```

## Automated performance and memory reports

Every full controller pull-request gate now attaches `resources-platform-verify-debian13-{amd64,arm64}`,
`resources-packaging-debian13-{amd64,arm64}`, and
`resources-coverage-debian13-amd64`, with a readable GitHub job summary.
Each artifact contains `report.md`, versioned `report.json`, the original
`command.log`, and any test lifecycle snapshots. Failed commands still produce
reports and keep their original failure status. The suite is unchanged: reports
observe the existing commands rather than running a second benchmark.

Start with the slowest Rust suites and largest sampled process contributors.
Compiler/build memory is separate from the test process; fixture waits are not
audio processing time. The controller's existing 2000-peer admission regression
optionally records baseline, admitted, stopped and fixture-dropped observations.
Compare RSS with glibc arena-in-use, free-retained and mmap totals to distinguish
retained allocator storage from a live-allocation lead. These are aggregate
observations, not allocation call stacks or proof of a leak. The admission
fixture keeps all 2000 sessions and 48 kHz buffers, but does not run 2000 active
audio streams. The test-only recorder never trims memory or changes allocator
settings. Serial tests avoid unrelated tests contaminating lifecycle comparisons.

Existing detailed audio measurements are reused, not replaced:
`rpt_advanced/tests/peer_egress_load.py` emits real loopback egress throughput,
callback/queue latency and loss JSON; USBRadioPlus's
`tests/test_rms_agc_ladspa.c` reports CPU cost for voiced audio and silence.
The loopback experiment remains opt-in. To measure it locally, put this
repository's reporter in the mounted development workspace and wrap the existing
command, for example inside a maintained labeled quality container:

```sh
python3 workflows/tools/resource_report.py --label loopback-1000-release \
  --output .work/resource-reports/loopback-1000-release -- \
  python3 tests/peer_egress_load.py --peers 1000 --seconds 120 \
  --output .work/loopback-1000.json
```

Use an empty output directory for each run; stale reports are rejected.
Respect the constrained launcher and coordinate local runs on shared hosts.
Reporting itself starts no per-peer threads and samples process statistics every
250 ms. No timing or memory thresholds replace functional assertions.

Compare only matching workload/source/dependency/build/architecture identities,
CPU and memory limits, allocator settings and cache conditions. The report stores
Cargo/dependency hashes, dependency manifest contents, installed package versions,
compiler versions, CPU affinity/quota and memory/swap/pid limits. Local launcher
runs record the freshly pulled immutable image digest. Hosted container jobs
record the image tag and package inventory; when an immutable digest is not
available, the report says so. Dependency source pins may be unpublished
candidates; neither the reporter nor its package inventory asserts release status.

Kernel `wait4` high-water RSS is the largest child/descendant process, not total
concurrent usage. Sampled process-tree RSS can miss short peaks and double-counts
shared pages. Lifecycle RSS includes fixture storage and process history; glibc
counters have tcache/other-allocator limits. Coverage and optimized/debug runs
are separate workloads. Missing observations are unavailable, never estimated
as zero, and abrupt OOM/SIGKILL of the reporter can prevent final artifacts.
