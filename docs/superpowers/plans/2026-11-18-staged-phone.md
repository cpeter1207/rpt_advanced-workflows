# Staged phone qualification implementation plan

Goal: implement the reviewed docs/phone-staged-cohort-design.md without publishing
or compiling locally. Native execution remains gated on final independent review
and approval. Controller readiness pin is bc46f631d8da28fd69b41e4e1c33c7e3410d163b;
five provider pins and IAX remain as specified in the design.

1. Write failing unit tests for exact source/manifest and package-set validation,
   same-version replacement, installed byte verification, loader escape rejection.
   Implement tools/staged_phone.py and tools/test_staged_phone.py. Use actual
   temporary files for byte checks; mock dpkg only at its command boundary.
2. Add qualification/phone-staged.json and baseline manifest snapshot. Keep the
   original phone-downlink.json unchanged. Freeze dependency installer SHA before
   use; do not execute a moving main action. Tests reject unpinned action inputs.
3. Implement narrowly scoped package builder and receipts. Native CI only: verify
   architecture/image/disk, build/install exact packages in dependency order,
   audit selected installed bytes before and after each gate. Provider check and
   package targets must not publish or perform coverage on arm64.
4. Implement ordinary controller quality/platform/package/coverage gates and the
   52 installed-provider tests. Compile test binaries with --no-run and execute
   them directly with installed paths; capture dynamic loader paths and hash
   actual loaded candidate bytes. Reject stale alternate roots.
5. Add manual-only workflow with immutable native image selection and isolated
   artifacts. Run Python regression suites, syntax/lint/actionlint when available,
   then freeze for independent implementation review. Do not invoke hosted CI.

Review focus: duplicate package names with same versions; missing required
provider artifacts; path/symlink escapes; cargo-injected build-tree load paths;
partial/skipped jobs mistakenly reported successful. Tests must fail each case.
