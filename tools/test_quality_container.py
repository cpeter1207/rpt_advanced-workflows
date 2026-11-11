"""Verify constrained launcher arguments without starting Docker."""

import fcntl
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("run-in-quality-container.sh")


class LauncherTests(unittest.TestCase):
    def run_launcher(
        self, profile="constrained", socket="0", pull="1", result=0, locked=False
    ):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            docker = root / "docker"
            docker.write_text("""#!/usr/bin/python3
import json, os, sys
with open(os.environ["CAPTURE"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
args = sys.argv[1:]
if args[:2] == ["image", "pull"]:
    print("Digest: sha256:" + "a" * 64)
if args and args[0] == "run":
    open(args[args.index("--cidfile") + 1], "w").write("test-owned-container")
    sys.exit(int(os.environ["RESULT"]))
""")
            docker.chmod(0o755)
            capture = root / "capture"
            lock_dir = root / ".cache/rpt-advanced"
            lock_dir.mkdir(parents=True)
            lock = (lock_dir / "constrained.lock").open("w")
            self.addCleanup(lock.close)
            if locked:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            env = dict(
                os.environ,
                HOME=str(root),
                PATH=f"{root}:/usr/bin:/bin",
                CAPTURE=str(capture),
                RESULT=str(result),
                RPTADV_CONTAINER_PROFILE=profile,
                RPTADV_CONTAINER_DOCKER_SOCKET=socket,
                RPTADV_CONTAINER_PULL=pull,
            )
            completed = subprocess.run(
                [
                    "sh",
                    str(SCRIPT),
                    "example:latest",
                    str(root),
                    "printf",
                    "one argument",
                ],
                env=env,
                check=False,
                text=True,
                capture_output=True,
            )
            calls = (
                [json.loads(x) for x in capture.read_text().splitlines()]
                if capture.exists()
                else []
            )
            return completed, calls

    def test_constrained_limits_and_serial_work_are_enforced(self):
        completed, calls = self.run_launcher()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        args = next(c for c in calls if c[0] == "run")
        for flag, value in [
            ("--cpus", "1"),
            ("--memory", "1536m"),
            ("--memory-swap", "1536m"),
            ("--pids-limit", "256"),
        ]:
            self.assertIn(flag, args)
            self.assertEqual(args[args.index(flag) + 1], value)
        for item in ["CARGO_BUILD_JOBS=1", "RUST_TEST_THREADS=1", "OMP_NUM_THREADS=1"]:
            self.assertIn(item, args)
        image_index = next(
            i for i, a in enumerate(args) if a.startswith("example:latest@sha256:")
        )
        self.assertEqual(
            args[image_index + 1 :],
            [
                "timeout",
                "--signal=TERM",
                "--kill-after=15s",
                "20m",
                "printf",
                "one argument",
            ],
        )
        self.assertIn(["container", "rm", "--force", "test-owned-container"], calls)
        self.assertTrue(any(c[:2] == ["image", "pull"] for c in calls))

    def test_default_profile_preserves_unlimited_command(self):
        completed, calls = self.run_launcher("default")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        args = next(c for c in calls if c[0] == "run")
        self.assertNotIn("--memory", args)
        self.assertEqual(args[-2:], ["printf", "one argument"])

    def test_allocator_thresholds_are_constrained_only(self):
        for profile in ("constrained", "default"):
            with self.subTest(profile=profile):
                completed, calls = self.run_launcher(profile)
                self.assertEqual(completed.returncode, 0, completed.stderr)
                args = next(c for c in calls if c[0] == "run")
                for setting in (
                    "MALLOC_MMAP_THRESHOLD_=131072",
                    "MALLOC_TRIM_THRESHOLD_=131072",
                ):
                    self.assertEqual(setting in args, profile == "constrained")

    def test_invalid_profile_fails_before_docker(self):
        completed, calls = self.run_launcher("typo")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(calls, [])

    def test_constrained_disallows_docker_socket(self):
        completed, calls = self.run_launcher(socket="1")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(calls, [])

    def test_constrained_requires_fresh_pull(self):
        completed, calls = self.run_launcher(pull="0")
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(calls, [])

    def test_concurrent_constrained_run_is_rejected(self):
        completed, calls = self.run_launcher(locked=True)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(calls, [])

    def test_failure_propagates_and_cleans_own_container(self):
        completed, calls = self.run_launcher(result=124)
        self.assertEqual(completed.returncode, 124)
        self.assertIn(["container", "rm", "--force", "test-owned-container"], calls)


class ImageDefaultsTests(unittest.TestCase):
    def test_quality_and_test_images_default_to_serial_work(self):
        for name in ("quality.Dockerfile", "test.Dockerfile"):
            with self.subTest(image=name):
                contents = (SCRIPT.parent.parent / "containers" / name).read_text()
                for assignment in (
                    "CARGO_BUILD_JOBS=1",
                    "RUST_TEST_THREADS=1",
                    "OMP_NUM_THREADS=1",
                    "OPENBLAS_NUM_THREADS=1",
                ):
                    self.assertIn(assignment, contents)


if __name__ == "__main__":
    unittest.main()
