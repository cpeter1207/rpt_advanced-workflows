# CI-only phone downlink qualification

This narrowly triggered workflow does not release packages, update APT, build
published images, merge branches, install on nodes or access physical radios.
It retains diagnostic logs and source/architecture/hash manifests only. It is
not the required full quality gate and cannot authorize a release.

The manifest pins all six project source repositories by commit. Each native
Debian 13 job builds its own dynamic candidate libraries in a private directory,
checks ELF architecture and transitive dependency resolution, and records the
resolved quality image, package inventory, source commits and binary hashes
before and after five downlink and two native SIP loopback tests. Zero/ignored
selections and binary changes fail. Existing fixed-amd64 C5 runners are unchanged.

Prerequisites before invocation:
1. Independently review these workflow changes and run workflow validation.
2. Make all pinned source commits reachable on deliberately chosen qualification
   branches only after their applicable preflight checks. This is source
   publication, not release qualification. Do not update main, existing PR heads,
   tags, APT or release assets merely to make these commits reachable.
3. Push the reviewed workflow commit only to
   qualification/phone-downlink-20261117 in the workflow repository. That exact
   branch push starts this diagnostic job without changing the default branch.
   Record its resolved SHA. Manual dispatch remains available only after normal
   default-branch registration; it is not needed for this qualification run.
4. The current signed baseline dependencies and private Sofia action must succeed.
   The source codec build verifies its declared upstream archives. The runner
   must have access to those sources. No secrets or provider accounts are used.

Current local preparation has NOT yet run the full six-source native build.
It has only exercised helper contracts and static workflow/script checks.
The first native build may reveal missing image prerequisites, resource limits
or source composition errors. Report those as failures, not a reason to weaken
checks. Hardware acceptance, production coverage, complete core/product suites,
packaging and the broader C5 matrix remain separate required work.

Rust compilation and tests inherit RUSTFLAGS with -Dwarnings appended.
CARGO_ENCODED_RUSTFLAGS is rejected before building because it would override
provider Makefile SONAME flags; callers must use RUSTFLAGS instead.
