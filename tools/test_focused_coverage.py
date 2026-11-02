"""Focused coverage is diagnostic; it must not replace the complete gate."""

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/focused-tests.yml"


class FocusedCoverage(unittest.TestCase):
    def test_integration_uses_make_sdk_scope_and_preserves_failure(self):
        source = WORKFLOW.read_text()
        scripts = []
        for name in ("Validate selection", "Run selected verification"):
            step = source.split(f"      - name: {name}\n", 1)[1]
            step = step.split("      - ", 1)[0]
            scripts.append(textwrap.dedent(step.split("        run: |\n", 1)[1]))
        for status in (0, 37):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as work:
                root = Path(work)
                make = root / "make"
                make.write_text(
                    '#!/bin/sh\nprintf "%s\\n" "$*" >> "$MAKE_LOG"\n'
                    'printf "%s\\n" "${RPT_ADVANCED_LIBDIR-unset}" >> "$SDK_LOG"\n'
                    'exit "$MAKE_STATUS"\n'
                )
                make.chmod(0o755)
                cargo = root / "cargo"
                cargo.write_text("#!/bin/sh\nexit 99\n")
                cargo.chmod(0o755)
                result = subprocess.run(
                    ["bash", "-c", "\n".join(scripts)],
                    cwd=root,
                    env=dict(
                        os.environ,
                        PATH=f"{root}:{os.environ['PATH']}",
                        CODE_REF="a" * 40,
                        CHECK="integration",
                        PACKAGE="rpt-advanced-core",
                        TEST_FILTER="",
                        RPT_ADVANCED_LIBDIR="/installed/sdk",
                        MAKE_LOG=str(root / "make.log"),
                        SDK_LOG=str(root / "sdk.log"),
                        MAKE_STATUS=str(status),
                    ),
                    check=False,
                )
                self.assertEqual(result.returncode, status)
                self.assertEqual((root / "make.log").read_text().strip(), "integration")
                self.assertEqual((root / "sdk.log").read_text().strip(), "unset")

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
            "options: [tests, preflight, rustdoc, coverage, integration]",
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
