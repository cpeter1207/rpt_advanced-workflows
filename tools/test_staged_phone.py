"""Fast, non-installing regression tests for staged phone package identity."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import staged_phone as staged


class StagedPhoneTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads(
            (Path(__file__).resolve().parents[1] / "qualification/phone-downlink.json").read_text()
        )
        self.manifest["controller"]["sha"] = staged.CONTROLLER

    def test_exact_cohort(self):
        staged.validate_sources(self.manifest)

    def test_provider_drift(self):
        for role in self.manifest:
            bad = copy.deepcopy(self.manifest)
            bad[role]["sha"] = "f" * 40
            with self.subTest(role=role), self.assertRaises(ValueError):
                staged.validate_sources(bad)

    def test_missing_role(self):
        del self.manifest["sdk"]
        with self.assertRaises(ValueError):
            staged.validate_sources(self.manifest)

    def test_mutable_source(self):
        self.manifest["sdk"]["sha"] = "main"
        with self.assertRaises(ValueError):
            staged.validate_sources(self.manifest)

    def test_same_version_candidate_replaces_baseline_by_name(self):
        old = {"package": "libexample1", "version": "1", "arch": "amd64", "sha256": "old"}
        new = dict(old, sha256="new")
        self.assertEqual(staged.merge_packages([old], [new], "amd64"), [new])

    def test_duplicate_baseline_or_candidate_rejected(self):
        item = {"package": "libexample1", "version": "1", "arch": "amd64"}
        for baseline, candidate in [([item, item], []), ([], [item, item])]:
            with self.assertRaises(ValueError):
                staged.merge_packages(baseline, candidate, "amd64")

    def test_wrong_architecture_rejected(self):
        item = {"package": "libexample1", "version": "1", "arch": "arm64"}
        with self.assertRaises(ValueError):
            staged.merge_packages([], [item], "amd64")

    def test_byte_proof_rejects_stale_same_version_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "usr/lib/example.so.1"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"candidate")
            expected = {"usr/lib/example.so.1": hashlib.sha256(b"candidate").hexdigest()}
            self.assertEqual(staged.verify_files(root, expected), expected)
            path.write_bytes(b"baseline")
            with self.assertRaises(ValueError):
                staged.verify_files(root, expected)

    def test_path_and_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["../escape", "/etc/passwd"]:
                with self.assertRaises(ValueError):
                    staged.verify_files(root, {name: "bad"})
            (root / "escape").symlink_to("/etc/passwd")
            with self.assertRaises(ValueError):
                staged.verify_files(root, {"escape": "bad"})

    def test_loader_requires_actual_initialization_not_search_attempt(self):
        log = " 123: trying file=/tmp/build/librptadv_product.so.3\n"
        self.assertEqual(staged.loaded_paths(log), set())
        log += " 123: calling init: /usr/lib/aarch64-linux-gnu/librptadv_product.so.3\n"
        self.assertEqual(staged.loaded_paths(log), {Path("/usr/lib/aarch64-linux-gnu/librptadv_product.so.3")})

    def test_loaded_candidate_must_match_package_path_and_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "libexample.so.1"
            path.write_bytes(b"correct")
            expected = {str(path): hashlib.sha256(b"correct").hexdigest()}
            self.assertEqual(staged.verify_loaded({path}, expected), expected)
            with self.assertRaises(ValueError):
                staged.verify_loaded({root / "stale/libexample.so.1"}, expected)
            path.write_bytes(b"stale")
            with self.assertRaises(ValueError):
                staged.verify_loaded({path}, expected)

    def test_loaded_candidate_cannot_be_missing(self):
        with self.assertRaises(ValueError):
            staged.verify_loaded(set(), {"/usr/lib/libexample.so.1": "hash"})


if __name__ == "__main__":
    unittest.main()
