"""Validate the package build plan without executing builds or installs."""
import json
import unittest
from pathlib import Path

import staged_packages as packages


class PackagePlanTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.baseline = json.loads((root / "qualification/phone-staged-baseline.json").read_text())

    def test_dependency_order(self):
        self.assertEqual(packages.ORDER, ("rnnoise", "codec", "radio", "adapter", "sdk"))

    def test_only_product_sdk_packages_installed(self):
        self.assertEqual(packages.required_packages("sdk", self.baseline),
                         {"libusbradioplus-product1", "libusbradioplus-product-dev"})

    def test_existing_codec_binary_selection_preserved(self):
        expected = next(x["packages"] for x in self.baseline if x["repository"] == "rptadv-codec-adapters")
        self.assertEqual(packages.required_packages("codec", self.baseline), set(expected))

    def test_unknown_role_cannot_request_arbitrary_packages(self):
        with self.assertRaises(ValueError):
            packages.required_packages("iax", self.baseline)

    def test_native_guard_rejects_non_disposable_or_wrong_arch(self):
        for environment, actual in [({}, "amd64"), ({"GITHUB_ACTIONS": "true", "STAGED_PHONE_DISPOSABLE": "1"}, "arm64")]:
            with self.assertRaises(ValueError):
                packages.validate_guard(environment, "amd64", actual, "13")

    def test_native_guard_accepts_only_debian13(self):
        env = {"GITHUB_ACTIONS": "true", "STAGED_PHONE_DISPOSABLE": "1"}
        packages.validate_guard(env, "arm64", "arm64", "13")
        with self.assertRaises(ValueError):
            packages.validate_guard(env, "arm64", "arm64", "12")


if __name__ == "__main__":
    unittest.main()
