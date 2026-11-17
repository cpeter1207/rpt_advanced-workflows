"""Reject mutable, mismatched and zero-test CI cohort inputs."""

import copy
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

import phone_cohort as cohort


class CohortTests(unittest.TestCase):
    """Small contract tests for source and binary identity."""

    def test_manifest_requires_every_fixed_role_and_immutable_sha(self):
        good = {
            key: {"repository": repo, "sha": "a" * 40}
            for key, repo in cohort.REPOSITORIES.items()
        }
        cohort.validate_manifest(good)
        for role in good:
            for field, value in (("sha", "main"), ("repository", "other/repo")):
                bad = copy.deepcopy(good)
                bad[role][field] = value
                with self.assertRaises(ValueError):
                    cohort.validate_manifest(bad)
            bad = copy.deepcopy(good)
            del bad[role]
            with self.assertRaises(ValueError):
                cohort.validate_manifest(bad)
        with self.assertRaises(ValueError):
            cohort.validate_manifest({**good, "extra": good["sdk"]})

    def test_native_elf_machine_not_filename_decides_architecture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fake-arm64.so"
            for arch, machine in (("amd64", 62), ("arm64", 183)):
                data = bytearray(64)
                data[:6] = b"\x7fELF\x02\x01"
                struct.pack_into("<H", data, 18, machine)
                path.write_bytes(data)
                cohort.verify_elf(path, arch)
                other = "amd64" if arch == "arm64" else "arm64"
                with self.assertRaises(ValueError):
                    cohort.verify_elf(path, other)
            path.write_bytes(b"not an ELF library")
            with self.assertRaises(ValueError):
                cohort.verify_elf(path, "amd64")

    def test_indented_ldd_entries_and_candidate_escape_are_checked(self):
        output = "  libone.so.1 => /candidate/libone.so.1 (0x0)\n\tlibtwo.so.2 => /usr/lib/libtwo.so.2 (0x0)"
        self.assertEqual(
            cohort.dependencies(output),
            {
                "libone.so.1": "/candidate/libone.so.1",
                "libtwo.so.2": "/usr/lib/libtwo.so.2",
            },
        )
        with self.assertRaises(ValueError):
            cohort.dependencies("  libone.so.1 => not found")

    def test_source_identity_rejects_wrong_commit_and_tracked_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)

            def git(*args):
                return subprocess.check_output(
                    ["git", "-C", str(root), *args], text=True
                ).strip()

            git("init", "-q")
            source = root / "source.txt"
            source.write_text("reviewed")
            git("add", "source.txt")
            git(
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "-qm",
                "fixture",
            )
            sha = git("rev-parse", "HEAD")
            cohort.verify_source(root, sha)
            with self.assertRaises(ValueError):
                cohort.verify_source(root, "0" * 40)
            source.write_text("changed")
            with self.assertRaises(ValueError):
                cohort.verify_source(root, sha)

    def test_workflow_is_dispatch_only_and_uploads_no_binaries(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/phone-cohort.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("write", workflow)
        self.assertNotIn("qualification-output/runtime", workflow)
        self.assertIn("ubuntu-24.04-arm", workflow)

    def test_zero_failed_ignored_and_wrong_counts_are_not_passes(self):
        cohort.require_tests("test result: ok. 5 passed; 0 failed; 0 ignored;", 5)
        for value in (
            "0 passed; 0 failed; 0 ignored;",
            "5 passed; 1 failed; 0 ignored;",
            "5 passed; 0 failed; 1 ignored;",
            "6 passed; 0 failed; 0 ignored;",
        ):
            with self.assertRaises(ValueError):
                cohort.require_tests("test result: ok. " + value, 5)


if __name__ == "__main__":
    unittest.main()
