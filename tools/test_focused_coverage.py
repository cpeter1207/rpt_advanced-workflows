"""Focused coverage is diagnostic; it must not replace the complete gate."""

import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/focused-tests.yml"


class FocusedCoverage(unittest.TestCase):
    def test_failed_selected_tests_still_report_and_remain_failed(self):
        source = WORKFLOW.read_text()
        self.assertIn("|| test_status=$?", source)
        self.assertLess(
            source.index("|| test_status=$?"),
            source.index("cargo llvm-cov report --release"),
        )
        self.assertLess(
            source.index("cargo llvm-cov report --release"),
            source.index('exit "$test_status"'),
        )

    def test_coverage_is_selectable_and_retains_its_report(self):
        source = WORKFLOW.read_text()
        for required in [
            "options: [tests, preflight, rustdoc, coverage]",
            "if: always() && inputs.check == 'coverage'",
            "build/coverage/focused.json",
        ]:
            self.assertTrue(required in source, required)

    def test_changed_adapter_packages_can_be_measured_separately(self):
        source = WORKFLOW.read_text()
        for package in [
            "rptadv-asterisk-adapter",
            "rptadv-jitter-adapter",
            "rptadv-file-adapter",
            "rptadv-speech-adapter",
        ]:
            self.assertEqual(source.count(package), 2)

    def test_coverage_uses_one_instrumented_generation_and_selected_tests(self):
        source = WORKFLOW.read_text()
        for required in [
            "export RUSTUP_TOOLCHAIN=nightly-2025-02-20",
            'export CARGO_LLVM_COV_TARGET_DIR="$CARGO_TARGET_DIR"',
            "llvm-cov show-env --branch --export-prefix",
            'cargo test --locked --release -p "$PACKAGE" "$TEST_FILTER"',
        ]:
            self.assertTrue(required in source, required)


if __name__ == "__main__":
    unittest.main()
