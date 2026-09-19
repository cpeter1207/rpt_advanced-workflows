#!/usr/bin/env python3
"""Exercise the release build step's package handoff to artifact upload."""

import os
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path


def main():
    """Require an upload-safe glob that includes the builder's package bytes."""
    workflow = Path(".github/workflows/release.yml").read_text()
    build = workflow.split("      - name: Build Debian packages\n", 1)[1]
    run = build.split("      - uses:", 1)[0].split("run:", 1)[1].strip()
    if run.startswith("|\n"):
        run = textwrap.dedent(run[2:])
    upload = workflow.split("uses: actions/upload-artifact@", 1)[1]
    pattern = re.search(r"^\s+path: (.+)$", upload, re.MULTILINE).group(1)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        workspace = root / "workspace"
        workspace.mkdir()
        builder = root / "dpkg-buildpackage"
        builder.write_text(
            "#!/bin/sh\nprintf package > ../rpt-advanced_test_amd64.deb\n"
        )
        builder.chmod(0o755)
        subprocess.run(
            ["sh", "-ec", run],
            cwd=workspace,
            env={**os.environ, "PATH": f"{root}:{os.environ['PATH']}"},
            check=True,
        )
        assert not ({".", ".."} & set(pattern.split("/"))), "unsafe upload path"
        packages = list(workspace.glob(pattern))
        assert len(packages) == 1, "built package missing from upload glob"
        assert packages[0].read_text() == "package"
    print("Release artifact path regression passed")


if __name__ == "__main__":
    main()
