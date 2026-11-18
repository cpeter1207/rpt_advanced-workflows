# Extra prerequisite evidence, not part of the original six-source cohort

## Sofia: existing upstream Debian packaging

Read-only verification found v1.13.19 is commit
6dce59d35535e6dd3945c7b0f76dbf1ba884202d (git ls-remote verified).
It already contains debian/control, debian/rules, install manifests and copyright.
Changelog version is 1.13.19-0. Runtime libsofia-sip-ua0 and development
libsofia-sip-ua-dev have the real required names and an exact-version dependency.
Use this packaging rather than generate fake equivs or disable dependency checks.
The upstream Debian 13 ARM recipe installs build dependencies with mk-build-deps
and runs debuild; hosted native builds can reuse that pattern without its image
publication or global Git trust settings.

Two differences require explicit implementation review before a final package
recipe: debian/rules passes --disable-stun, while earlier private CI Sofia used
upstream defaults; override_dh_auto_test is empty. Preserve the former tested
feature configuration with a minimal packaging-only adjustment if needed and
run actual upstream tests separately. Do not silently label this configuration
identical or its package build as test coverage. The source archive hash already
used by private CI is 99389b574dfcff5775b260dd9ef1bdd2bcb5a42e655bd229d477e488e658064f.
No source, package, or image was built during this investigation.

## RNNoise: reuse native project Docker testbed

Candidate Makefile platform-verify expands to test, install-check, autopkgtest,
and distcheck. autopkgtest invokes its Docker backend and allows
AUTOPKGTEST_TESTBED_IMAGE to be overridden. Its default QUALITY_IMAGE is local,
not a confirmed published registry image. The project workflow already selects
native_docker_socket:true in the shared quality workflow.

Reuse the exact candidate containers/quality.Dockerfile on each native hosted
runner, override BASE_IMAGE to an immutable reviewed multiarch/platform digest,
and record the locally built image ID before passing that ID to autopkgtest.
No testbed publication is needed. Its recipe supplies autopkgtest/docker-cli,
packaged underlying librnnoise0/dev, and removes documented unmanaged /usr/local
RNNoise leftovers. The staged signed-APT bootstrap now also requests the real
librnnoise-dev package, not only runtime. Actual archive availability/version and
native build success remain unverified; the gate must fail if missing.

Retain the upstream archive checksum and recipe/source hashes in receipts. A
Docker socket belongs only to disposable hosted test runners, never the live
node or this low-disk development host. Do not use the constrained local launcher
profile with a socket: it explicitly forbids that combination. Existing default
launcher supports the socket. If feeding an already resolved image digest to
that launcher, pre-pull it and set RPTADV_CONTAINER_PULL=0 because its pull path
otherwise appends another @digest to the input.
