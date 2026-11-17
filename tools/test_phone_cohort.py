"""Reject mutable, mismatched and zero-test CI cohort inputs."""

import copy
import hashlib
import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_workflow_has_only_isolated_push_and_uploads_no_binaries(self):
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/phone-cohort.yml").read_text()
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertIn(
            "push:\n    branches: [qualification/phone-downlink-20261117]", workflow
        )
        self.assertNotIn("branches: [main]", workflow)
        self.assertNotIn("tags:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("write", workflow)
        self.assertNotIn("qualification-output/runtime", workflow)
        self.assertIn("ubuntu-24.04-arm", workflow)

    def test_warning_policy_preserves_flags_and_rejects_encoded_override(self):
        script = Path(__file__).with_name("run_phone_cohort.sh").read_text()
        policy = script.split("# BEGIN Rust warning policy")[1].split(
            "# END Rust warning policy"
        )[0]
        env = {**os.environ, "RUSTFLAGS": "-C opt-level=1 -Awarnings"}
        env.pop("CARGO_ENCODED_RUSTFLAGS", None)
        result = subprocess.run(
            ["bash", "-eu", "-c", policy + '\nprintf "%s" "$RUSTFLAGS"'],
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(result.stdout, "-C opt-level=1 -Awarnings -Dwarnings")
        env["CARGO_ENCODED_RUSTFLAGS"] = ""
        result = subprocess.run(
            ["bash", "-eu", "-c", policy],
            check=False,
            env=env,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CARGO_ENCODED_RUSTFLAGS", result.stderr)

    def test_receipt_rejects_candidate_dependency_outside_private_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory)
            names = (
                "librptadv_product.so.3",
                "libusbradioplus_product.so.1",
                "librptadv_portaudio_alsa_adapter.so.2",
                "librptadvradio.so.5",
                "librptadv_rnnoise_adapter.so.1",
                "librptadv_codec_g711.so.1",
                "librptadv_sip_adapter.so.1",
                "usbradioplus_agc.so",
            )
            for name in names:
                (runtime / name).write_bytes(b"fixture")

            def command(args, cwd=None):
                if args[0] == "dpkg":
                    return "amd64"
                if args[0] == "ldd":
                    return "  librptadvradio.so.5 => /usr/lib/librptadvradio.so.5 (0x0)"
                raise AssertionError(args)

            with (
                mock.patch.object(cohort, "command", side_effect=command),
                mock.patch.object(cohort, "verify_elf"),
                self.assertRaisesRegex(ValueError, "candidate dependency escaped"),
            ):
                cohort.receipt(
                    {},
                    runtime,
                    runtime,
                    "amd64",
                    "ghcr.io/cpeter1207/rpt-advanced-quality-debian13@sha256:"
                    + "a" * 64,
                )

    def test_regressions_are_wired_into_both_workflows(self):
        root = Path(__file__).resolve().parents[1]
        for name in ("validate.yml", "phone-cohort.yml"):
            workflow = (root / ".github/workflows" / name).read_text()
            self.assertIn("python3 tools/test_phone_cohort.py", workflow)

    def test_pinned_headers_reject_changed_content_and_record_provenance(self):
        data = b"verified header"
        digest = hashlib.sha256(data).hexdigest()
        inputs = {
            "remote/header.h": {
                "repository": "example/repo",
                "sha": "a" * 40,
                "sha256": digest,
            }
        }
        with (
            tempfile.TemporaryDirectory() as directory,
            mock.patch.object(cohort, "HEADER_INPUTS", inputs),
        ):
            root = Path(directory)
            response = mock.MagicMock()
            response.__enter__.return_value.read.return_value = data
            with mock.patch.object(
                cohort.urllib.request, "urlopen", return_value=response
            ):
                cohort.prepare_headers(root)
            self.assertEqual(cohort.header_receipt(root), inputs)
            (root / "remote/header.h").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "header hash"):
                cohort.header_receipt(root)
            response.__enter__.return_value.read.return_value = b"wrong download"
            with (
                mock.patch.object(
                    cohort.urllib.request, "urlopen", return_value=response
                ),
                self.assertRaisesRegex(ValueError, "header hash"),
            ):
                cohort.prepare_headers(root)

    def test_candidate_provider_includes_precede_all_builds(self):
        script = Path(__file__).with_name("run_phone_cohort.sh").read_text()
        policy = script.split("# BEGIN candidate provider includes")[1].split(
            "# END candidate provider includes"
        )[0]
        result = subprocess.run(
            ["bash", "-eu", "-c", policy + '\nprintf "%s" "$BINDGEN_EXTRA_CLANG_ARGS"'],
            env={
                **os.environ,
                "sources": "/exact/sources",
                "BINDGEN_EXTRA_CLANG_ARGS": "-I/verified/supplemental",
            },
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            result.stdout,
            "-I/exact/sources/adapter/include -I/exact/sources/radio/include "
            "-I/exact/sources/rnnoise/include -I/verified/supplemental",
        )
        self.assertLess(
            script.index("# END candidate provider includes"),
            script.index("make -j1 all"),
        )

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
