# Isolated staged phone candidate qualification

Status: design checkpoint; not implemented, run, published or deployment-ready.
Base workflow: 7a8a7ff3160a90f83d8bb9e763448b7be3577e04.

## Purpose and boundary

Produce a truthful private package-cohort gate for the RTP/shared-courtesy fix.
The existing 52-test native cohort proves selected behavior, not an installable
release. Preserve that workflow and its receipts. No main, release, signed-APT,
registry image, latest tag, node configuration or deployment changes. The new
workflow has no automatic push trigger while under review. Publication and a
hosted invocation require subsequent approval. Full IAX parity is not claimed;
its existing ce9fe2da0d8480c1503f5eb80c3c95d8ac2e5360 source stays unchanged.

## Chosen approach

Reuse the local baseline dependency action for unchanged dependencies, then
build and install exact-source private Debian packages for the five candidate
providers. Keep controller/source manifest separate from released dependency
metadata: no version-floor or release attestation is fabricated. Existing
candidate dependency machinery provides the packaging pattern, but its remote
whitelist excludes USBRadioPlus and RNNoise; do not silently edit that service
or send unsupported entries to it. Implement one narrowly allowlisted local
candidate builder with the same dpkg/mk-build-deps flow and explicit receipts.

Rejected alternatives: the unchanged test-images workflow resolves workflow
main and publishes latest; source-only private DSOs do not prove packaging;
downgrading codec/reset providers removes required API capabilities. Although
the adapter clock tail is optional, changing it now invalidates the tested
cohort and is not necessary for this increment.

## Exact sources and order

Use the existing validated six-role manifest, copied to a separate staged
manifest. The five provider hashes remain fixed:

* RNNoise b25f187d958c9866430bdf968c2b2bb579e5d667
* codec 8596809c3ff8493d705bc2f65371e9f0b6e4fef2
* radio 8c5b5b41bc054a98dc7d36a7f199089bdc82b3b3
* adapter 8dbf88fa929940f74e7b918e339edef503cca7f6
* USBRadioPlus SDK 3bcd75465120b87fabdf25a2b2e8c4a0e808e842

Build RNNoise before radio; install radio, codec and adapter before SDK. The
controller pin starts at 5e94f7df416e33c311b05d95a7ba56273d7077e7 but must be
replaced once by the independently frozen readiness revision before running.
Compare unchanged controller manifest entries including IAX exactly; fail on
unapproved drift. Verify each checkout SHA and tracked cleanliness before and
after builds, not just the manifest spelling.

## Job graph and actual gates

Resolve a single quality-image multiarchitecture index digest; record each
native job's architecture-specific image identity as well as that index. Run
only native amd64 and arm64 Debian 13 runners in disposable job containers.
There are no local build containers in this preparation increment.

1. Native package preparation per architecture: baseline dependency provisioning,
   then sequential exact-source candidate build/install. Capture stdout/stderr
   and exit codes per provider, archive selected .debs and receipts. No nocheck
   shortcut may substitute for required provider tests.
2. Platform-independent controller `make quality` once on amd64 using the
   prepared exact package set, including formatting, Cppcheck, Clang-Tidy and
   documentation. Provider applicable quality checks also once on amd64.
3. After independent checks succeed, native controller `make platform-verify`
   and `DEB_BUILD_OPTIONS=nocheck dpkg-buildpackage -us -uc -b` on each arch;
   packaging nocheck is only permitted after tests pass. Exercise actual
   package staged installation and public ABI, not merely unpack/file presence.
4. Controller production `make coverage` on amd64 only. Do not weaken/exclude
   uncovered production paths. Provider coverage, where required by its gate,
   is also amd64 only and separately reported.
5. Run the existing 52 phone selections against the installed candidate DSOs,
   not a second independently rebuilt private cohort. Preserve exact counts,
   original SIP assertions and actual-owner expiry coverage.

Provider gates must use audited native targets. RNNoise/radio/adapter have
`test`, `install-check` and package/autopkgtest/distcheck targets; codec has
`test`, `install-check`, `package-artifact-check`. USBRadioPlus's current
`platform-verify` embeds `coverage`, so it must NOT run blindly on arm64: use
its actual `check`, `validate-release`, and staged distcheck constituents,
with coverage separately on amd64. Record this explicit equivalence rather
than claim an unchanged SDK platform-verify invocation. Audit every invoked
target for publication side effects. Never invoke release-packages, CI image
push workflows, or registry login/push as a shortcut.

## Package identity and installed-state proof

Candidate versions overlap old artifacts. For every selected package require
one file with the exact Package name and target Architecture (or explicitly
allowed all), hash its bytes, and record Version without treating it as source
provenance. Extract and hash runtime ELF and development header bytes; validate
ELF machine/SONAME and expected package ownership. Keep candidates in a separate
directory. Compose a final package set by package identity, replacing baseline
entries by name; fail ambiguous duplicates instead of picking filenames.

Install selected files with explicit local paths and --reinstall, even when
Version equals the baseline. Verify actual installed file hashes equal those
from the selected .deb, including SDK headers, RNNoise, codec, radio and adapter.
Record dpkg status, ELF DT_NEEDED and actual loader resolution for controller,
SDK and providers. Reject candidate resolutions outside the installed selected
package paths, alternate stale /usr/local/private roots, unresolved libraries,
or wrong architecture. Repeat critical hashes and resolution after gates.

Receipt links exact workflow SHA, source SHAs, immutable image identity, build
commands, architecture, baseline manifest hash, package hashes, installed
headers/ELFs and loader resolutions. Diagnostic logs are retained on failure;
package artifacts are qualification-only and not ready for node installation.
No registry/image creation is required to prove this gate. A later hardware
test image would need its own approved immutable name and installation plan.

## Fail-closed safeguards and local tests

Warnings remain errors, preserving existing caller compiler flags. Pin or
record all reusable installer code rather than silently rely on moving main.
No source rewrite by format checks. Bound jobs, threads, timeouts and disk;
fail early rather than threaten services. No broad cleanup or cache deletion.

Fast regression tests must reject mutable/missing pins, IAX drift, wrong arch,
wrong/duplicate package identity, same-version stale installed bytes, wrong
header bytes, unresolved/escaped loader paths, missing evidence and skipped
required gates. Mock subprocesses for these contracts; fast tests do not claim
native package integration. Validate shell syntax, Python lint/tests, YAML and
actionlint locally without pulls or compilation. Independent review precedes
any hosted publication.

## Remaining decision and estimates

Controller readiness SHA is pending. Some provider gate targets may reveal
new defects; preserve exact source and fail rather than patch in the workflow.
Full controller 100% coverage can be a substantive blocker, not infrastructure
success. Initial workflow implementation/fast tests: approximately 2-4 hours
following this design review; hosted full package/gate duration is unmeasured
and may take several hours per architecture. This is not an ETA for live-node
or RF acceptance.
