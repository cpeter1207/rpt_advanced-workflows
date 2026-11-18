"""Fast, non-installing regression tests for staged phone package identity."""
import copy
import hashlib
import json
import subprocess
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

    def test_real_deb_inventory_and_installed_header_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            (source / "DEBIAN").mkdir(parents=True)
            (source / "DEBIAN/control").write_text(
                "Package: staged-fixture-dev\nVersion: 1\nArchitecture: all\n"
                "Maintainer: Test <test@example.invalid>\nDescription: test fixture\n"
            )
            header = source / "usr/include/example.h"
            header.parent.mkdir(parents=True)
            header.write_text("/* selected package */\n")
            package = root / "fixture.deb"
            subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(source), str(package)], check=True, capture_output=True)
            info = staged.package_info(package)
            self.assertEqual(info["package"], "staged-fixture-dev")
            self.assertEqual(info["arch"], "all")
            self.assertEqual(info["sha256"], staged.sha256(package))
            stage = root / "stage"
            files = staged.package_files(package, stage, "amd64")
            self.assertEqual(files, {"usr/include/example.h": staged.sha256(header)})
            staged.verify_files(stage, files)
            (stage / "usr/include/example.h").write_text("/* wrong header */")
            with self.assertRaises(ValueError):
                staged.verify_files(stage, files)

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

    def test_baseline_manifest_cannot_change_iax_or_other_sources(self):
        expected = [{"repository": "librptadviax2", "sha": "ce9fe2da0d8480c1503f5eb80c3c95d8ac2e5360", "packages": ["client"]}]
        staged.validate_baseline(expected, expected)
        changed = copy.deepcopy(expected)
        changed[0]["sha"] = "f" * 40
        with self.assertRaises(ValueError):
            staged.validate_baseline(changed, expected)

    def test_package_selection_rejects_missing_or_duplicate_required_artifacts(self):
        item = {"package": "libexample1", "arch": "amd64", "version": "1"}
        self.assertEqual(staged.select_packages([item], {"libexample1"}, "amd64"), [item])
        for items in ([], [item, item]):
            with self.assertRaises(ValueError):
                staged.select_packages(items, {"libexample1"}, "amd64")

    def test_loader_rejects_alternate_version_of_selected_dso(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "libexample.so.1.0"
            selected.write_bytes(b"selected")
            other = root / "libexample.so.1.1"
            other.write_bytes(b"other")
            with self.assertRaises(ValueError):
                staged.verify_loaded({selected, other}, {str(selected): staged.sha256(selected)})

    def test_bootstrap_includes_real_rnnoise_development_package(self):
        text = (Path(__file__).resolve().parents[1] / ".github/actions/bootstrap-staged-phone/action.yml").read_text()
        self.assertIn("librnnoise0 librnnoise-dev", text)
        self.assertIn("librnnoise-dev_*.deb", text)

    def test_bootstrap_installer_is_pinned_before_execution(self):
        text = (Path(__file__).resolve().parents[1] / ".github/actions/bootstrap-staged-phone/action.yml").read_text()
        self.assertIn("install-candidate-dependencies@0fd80670536df45efb5b9738e6c116f1f9527870", text)
        self.assertNotIn("@main", text)

    def test_loaded_candidate_cannot_be_missing(self):
        with self.assertRaises(ValueError):
            staged.verify_loaded(set(), {"/usr/lib/libexample.so.1": "hash"})


if __name__ == "__main__":
    unittest.main()
