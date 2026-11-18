"""Fast regression contracts for ordinary staged gate invocation."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import staged_gates as gates
from staged_phone import PINS


class StagedGateTests(unittest.TestCase):
    def test_prepared_receipt_binds_source_arch_image_and_workflow(self):
        receipt = {"architecture": "amd64", "image": "image@digest", "workflow_commit": "a" * 40,
                   "sources": {role: {"sha": sha} for role, sha in PINS.items()}, "baseline_sha256": "baseline"}
        gates.validate_prepared(receipt, "amd64", "image@digest", "a" * 40, "baseline")
        for field in ("architecture", "image", "workflow_commit", "baseline_sha256"):
            bad = copy.deepcopy(receipt)
            bad[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(ValueError):
                gates.validate_prepared(bad, "amd64", "image@digest", "a" * 40, "baseline")
        receipt["sources"]["controller"]["sha"] = "b" * 40
        with self.assertRaises(ValueError):
            gates.validate_prepared(receipt, "amd64", "image@digest", "a" * 40, "baseline")

    def test_testbed_binds_recipe_source_image_and_architecture(self):
        receipt = {"architecture": "arm64", "base": "base", "image_id": "local",
                   "workflow_commit": "workflow", "source_sha": PINS["rnnoise"], "recipe_sha256": "recipe"}
        gates.validate_testbed(receipt, "arm64", "base", "local", "workflow", "recipe")
        for field in receipt:
            bad = dict(receipt)
            bad[field] = "wrong"
            with self.subTest(field=field), self.assertRaises(ValueError):
                gates.validate_testbed(bad, "arm64", "base", "local", "workflow", "recipe")

    def test_independent_and_coverage_recheck_installed_bytes(self):
        for phase in ("independent", "coverage"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                (root / "qualification").mkdir()
                (root / "qualification/phone-staged-baseline.json").write_text("[]")
                (root / "sources/controller/.github").mkdir(parents=True)
                (root / "sources/controller/.github/dependencies.json").write_text("[]")
                (root / "staged-output").mkdir()
                measured = {"files_sha256": {"usr/lib/test.so": "hash"}}
                with (patch.object(gates, "guard"), patch.object(gates, "gate_plan", return_value=[]),
                      patch.object(gates, "restore", return_value=(["archive"], {})),
                      patch.object(gates, "installed_receipt", return_value=measured) as verify):
                    gates.execute(root, phase, "amd64", "image")
                verify.assert_called_once_with(["archive"], "amd64")
                self.assertEqual(json.loads((root / "staged-output" /
                                             (phase + "-installed-after.json")).read_text()), measured)

    def test_post_gate_byte_mismatch_propagates_without_success_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (patch.object(gates, "installed_receipt", side_effect=ValueError("changed bytes")),
                  self.assertRaises(ValueError)):
                gates.verify_after_gate(root, ["archive"], "amd64", "coverage")
            self.assertFalse((root / "staged-output/coverage-installed-after.json").exists())

    def test_arm_native_never_invokes_coverage(self):
        plan = gates.gate_plan("native", "arm64")
        self.assertNotIn(("sdk", ("make", "platform-verify")), plan)
        self.assertIn(("sdk", ("make", "check")), plan)
        self.assertIn(("controller", ("make", "platform-verify")), plan)
        self.assertFalse(any("coverage" in command for _, command in plan))

    def test_independent_runs_controller_quality_once(self):
        plan = gates.gate_plan("independent", "amd64")
        self.assertEqual(plan.count(("controller", ("make", "quality"))), 1)
        with self.assertRaises(ValueError):
            gates.gate_plan("independent", "arm64")

    def test_coverage_is_amd64_only_and_contains_controller(self):
        self.assertIn(("controller", ("make", "coverage")), gates.gate_plan("coverage", "amd64"))
        with self.assertRaises(ValueError):
            gates.gate_plan("coverage", "arm64")

    def test_no_release_target_in_any_gate(self):
        for phase in ("independent", "native", "coverage"):
            for _, command in gates.gate_plan(phase, "amd64"):
                self.assertFalse(any(item in {"release", "release-packages", "push", "publish"} for item in command))

    def test_missing_actual_sofia_package_pair_is_rejected(self):
        with self.assertRaises(ValueError):
            gates.require_sofia_pair([])
        with self.assertRaises(ValueError):
            gates.require_sofia_pair([{"package": "libsofia-sip-ua0", "version": "1.13.19"}])

    def test_old_sofia_package_version_is_rejected(self):
        packages = [{"package": name, "version": "1.12.11"} for name in gates.SOFIA_PACKAGES]
        with self.assertRaises(ValueError):
            gates.require_sofia_pair(packages)

    def test_real_versioned_pair_is_eligible_not_release_attestation(self):
        packages = [{"package": name, "version": "1.13.19-1"} for name in gates.SOFIA_PACKAGES]
        gates.require_sofia_pair(packages)


if __name__ == "__main__":
    unittest.main()
