"""Resource reporting observes real commands without weakening their status."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPORTER = Path(__file__).with_name("resource_report.py")


class ResourceReport(unittest.TestCase):
    def test_command_status_logs_and_measured_resources(self):
        for status in (0, 37):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as work:
                root = Path(work)
                summary = root / "summary.md"
                command = [
                    sys.executable,
                    str(REPORTER),
                    "--label",
                    "fixture",
                    "--output",
                    str(root / "report"),
                    "--",
                    sys.executable,
                    "-c",
                    (
                        "import sys,time; x=bytearray(8*1024*1024); "
                        "print('Running unittests fixture (target/debug/deps/fixture)'); "
                        "print('test result: ok. 2 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.25s'); "
                        f"print('retained log',flush=True); time.sleep(.3); sys.exit({status})"
                    ),
                ]
                result = subprocess.run(
                    command,
                    cwd=root,
                    capture_output=True,
                    text=True,
                    env=dict(os.environ, GITHUB_STEP_SUMMARY=str(summary)),
                    check=False,
                )
                self.assertEqual(result.returncode, status, result.stderr)
                data = json.loads((root / "report/report.json").read_text())
                self.assertEqual(data["exit_code"], status)
                self.assertGreater(data["measured"]["elapsed_seconds"], 0)
                self.assertGreater(
                    data["measured"]["largest_process_peak_rss_bytes"], 0
                )
                self.assertGreater(data["sampled"]["process_tree_peak_rss_bytes"], 0)
                self.assertTrue(data["sampled"]["contributors"])
                self.assertEqual(data["estimated"], {})
                self.assertEqual(data["rust_suites"][0]["passed"], 2)
                self.assertEqual(data["rust_suites"][0]["ignored"], 1)
                self.assertEqual(data["rust_suites"][0]["executed_tests_per_second"], 8)
                self.assertIn("retained log", (root / "report/command.log").read_text())
                self.assertIn("fixture", summary.read_text())
                self.assertIn("not a leak", summary.read_text())

    def test_signal_failure_still_writes_report(self):
        with tempfile.TemporaryDirectory() as work:
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPORTER),
                    "--label",
                    "signal",
                    "--output",
                    work,
                    "--",
                    "sh",
                    "-c",
                    "kill -TERM $$",
                ],
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 143, result.stderr)
            self.assertEqual(
                json.loads((Path(work) / "report.json").read_text())["exit_code"], 143
            )

    def test_missing_command_and_stale_output_are_not_success(self):
        with tempfile.TemporaryDirectory() as work:
            command = [
                sys.executable,
                str(REPORTER),
                "--label",
                "absent",
                "--output",
                work,
                "--",
                "/nonexistent/rpt-advanced-test-command",
            ]
            first = subprocess.run(command, capture_output=True, check=False)
            self.assertEqual(first.returncode, 127, first.stderr)
            report = Path(work) / "report.json"
            original = report.read_bytes()
            second = subprocess.run(command, capture_output=True, check=False)
            self.assertEqual(second.returncode, 2, second.stderr)
            self.assertEqual(report.read_bytes(), original)

    def test_lifecycle_snapshots_are_preserved_in_readable_summary(self):
        with tempfile.TemporaryDirectory() as work:
            snapshot = {
                "schema_version": 1,
                "workload": "admission-2000",
                "phase": "fixtures-dropped",
                "pid": 1,
                "elapsed_seconds": 1.0,
                "connected_peers": 0,
                "rss_bytes": 123456,
                "glibc": {
                    "arena_in_use_bytes": 1000,
                    "arena_free_retained_bytes": 9000,
                    "mmap_bytes": 0,
                },
            }
            script = (
                "import os,pathlib; p=pathlib.Path(os.environ['RPTADV_RESOURCE_SNAPSHOT_DIR']); "
                f"p.mkdir(); (p/'snapshot.json').write_text({json.dumps(json.dumps(snapshot))})"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPORTER),
                    "--label",
                    "snapshot",
                    "--output",
                    work,
                    "--",
                    sys.executable,
                    "-c",
                    script,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((Path(work) / "report.json").read_text())
            self.assertEqual(report["lifecycle"], [snapshot])
            summary = (Path(work) / "report.md").read_text()
            self.assertIn("fixtures-dropped", summary)
            self.assertIn("free retained", summary)

    def test_bad_snapshots_keep_failed_command_status_and_raw_artifacts(self):
        with tempfile.TemporaryDirectory() as work:
            script = (
                "import os,pathlib,sys; p=pathlib.Path(os.environ['RPTADV_RESOURCE_SNAPSHOT_DIR']); "
                "p.mkdir(); (p/'truncated.json').write_text('{'); "
                "(p/'missing.json').write_text('{}'); "
                "(p/'wrong-type.json').write_text('[]'); sys.exit(37)"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPORTER),
                    "--label",
                    "bad-snapshots",
                    "--output",
                    work,
                    "--",
                    sys.executable,
                    "-c",
                    script,
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 37, result.stderr)
            report = json.loads((Path(work) / "report.json").read_text())
            self.assertEqual(report["exit_code"], 37)
            self.assertEqual(report["lifecycle"], [])
            self.assertEqual(len(report["diagnostics"]), 3)
            self.assertEqual((Path(work) / "snapshots/truncated.json").read_text(), "{")
            self.assertIn(
                "Snapshot diagnostics", (Path(work) / "report.md").read_text()
            )

    def test_suite_reuses_workloads_and_uploads_even_on_failure(self):
        root = REPORTER.parents[1]
        source = (root / ".github/workflows/quality.yml").read_text()
        self.assertIn("command: make platform-verify", source)
        self.assertIn("command: make coverage", source)
        self.assertIn(
            "command: env DEB_BUILD_OPTIONS=nocheck dpkg-buildpackage -us -uc -b",
            source,
        )
        self.assertNotIn("--ignored", source)
        action = (root / ".github/actions/resource-report/action.yml").read_text()
        self.assertIn("if: always()", action)
        self.assertIn("actions/upload-artifact@v7", action)
        self.assertIn("if-no-files-found: error", action)


if __name__ == "__main__":
    unittest.main()
