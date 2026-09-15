#!/usr/bin/env python3
"""Exercise workspace-scoped launcher cleanup without a Docker daemon."""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

LAUNCHER = Path(__file__).resolve().parents[1] / "tools/run-in-quality-container.sh"
DOCKER = r"""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
with Path(os.environ["DOCKER_CALL_LOG"]).open("a", encoding="utf-8") as log:
    log.write(json.dumps(args) + "\n")
if args[:2] == ["image", "pull"]:
    print("Digest: sha256:pulled-image")
elif args[:2] == ["image", "inspect"]:
    print("sha256:test-image")
elif args[:2] == ["container", "ls"]:
    required = {
        "label=rpt_advanced.test=true",
        "label=org.rptadvanced.test.project=production",
        "status=exited",
        "status=dead",
    }
    if not required.issubset(args) or not any(
        arg.startswith("label=org.rptadvanced.test.scope=") for arg in args
    ):
        raise SystemExit(90)
    if os.environ["DOCKER_STALE"] == "1":
        print("stopped-scoped")
elif args[:1] == ["run"]:
    if os.environ["DOCKER_CREATE_CID"] == "1":
        Path(args[args.index("--cidfile") + 1]).write_text("created-test\n")
    raise SystemExit(int(os.environ["DOCKER_RUN_STATUS"]))
elif args[:2] == ["container", "rm"]:
    pass
else:
    raise SystemExit(91)
"""


class LauncherCleanupTest(unittest.TestCase):
    """Only remove the container which this launcher invocation created."""

    def run_launcher(self, status, *, create_cid, pull, stale=False):
        """Run with a strict fake Docker and return status, output, and calls."""
        with tempfile.TemporaryDirectory(prefix="rpt-advanced-workflows-") as directory:
            root = Path(directory)
            workspace = root / "production"
            workspace.mkdir()
            docker = root / "docker"
            docker.write_text(DOCKER, encoding="utf-8")
            docker.chmod(0o755)
            log = root / "calls.jsonl"
            environment = dict(
                os.environ,
                PATH=f"{root}{os.pathsep}{os.environ['PATH']}",
                DOCKER_CALL_LOG=str(log),
                DOCKER_CREATE_CID="1" if create_cid else "0",
                DOCKER_RUN_STATUS=str(status),
                DOCKER_STALE="1" if stale else "0",
            )
            if not pull:
                environment["RPTADV_CONTAINER_PULL"] = "0"
            else:
                environment.pop("RPTADV_CONTAINER_PULL", None)
            result = subprocess.run(
                ["sh", str(LAUNCHER), "test-image:latest", str(workspace), "true"],
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            return result, calls

    def test_default_pull_runs_the_reported_digest(self):
        """A tag pull must execute the immutable digest that it reported."""
        result, calls = self.run_launcher(0, create_cid=True, pull=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Using test-image:latest@sha256:pulled-image", result.stderr)
        self.assertIn(["image", "pull", "test-image:latest"], calls)
        run = next(call for call in calls if call[:1] == ["run"])
        self.assertIn("test-image:latest@sha256:pulled-image", run)

    def test_startup_removes_only_stopped_scoped_container(self):
        """Running and unrelated containers are excluded by the discovery filters."""
        result, calls = self.run_launcher(0, create_cid=True, pull=False, stale=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        removals = [call for call in calls if call[:2] == ["container", "rm"]]
        self.assertEqual(
            removals,
            [
                ["container", "rm", "stopped-scoped"],
                ["container", "rm", "--force", "created-test"],
            ],
        )

    def test_command_failure_removes_created_container_id(self):
        """The EXIT trap preserves a command failure and removes its CID only."""
        result, calls = self.run_launcher(17, create_cid=True, pull=False)
        self.assertEqual(result.returncode, 17, result.stderr)
        self.assertEqual(calls[-1], ["container", "rm", "--force", "created-test"])

    def test_name_collision_does_not_remove_existing_container(self):
        """A failed run which creates no CID must leave the existing name alone."""
        result, calls = self.run_launcher(125, create_cid=False, pull=False)
        self.assertEqual(result.returncode, 125, result.stderr)
        self.assertFalse(any(call[:2] == ["container", "rm"] for call in calls))


if __name__ == "__main__":
    unittest.main()
