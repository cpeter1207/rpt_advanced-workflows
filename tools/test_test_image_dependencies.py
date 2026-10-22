#!/usr/bin/env python3
"""Smoke-test the real image build stage with native scheduler alpha2 packages."""

import argparse
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    """Build only a synthetic Debian fixture, never the production checkout."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "packages", type=Path, help="native scheduler runtime/dev .debs"
    )
    packages = parser.parse_args().packages.resolve(strict=True)
    work = ROOT / ".work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="test-image-dependencies-", dir=work
    ) as temporary:
        directory = Path(temporary)
        production = directory / "production"
        (production / "debian/source").mkdir(parents=True)
        sources = {
            "debian/control": (
                "Source: rptadv-workflow-smoke\nSection: misc\nPriority: optional\n"
                "Maintainer: Workflow Test <test@example.invalid>\n"
                "Build-Depends: debhelper-compat (= 13), "
                "librptadvschedule-dev (>= 0.1.0~alpha2-1)\n"
                "Standards-Version: 4.7.0\n\n"
                "Package: rptadv-workflow-smoke\nArchitecture: all\n"
                "Description: dependency installation smoke fixture\n"
            ),
            "debian/changelog": (
                "rptadv-workflow-smoke (1.0) unstable; urgency=low\n\n"
                "  * Exercise image dependency installation.\n\n"
                " -- Workflow Test <test@example.invalid>  "
                "Wed, 21 Oct 2026 00:00:00 +0000\n"
            ),
            "debian/rules": "#!/usr/bin/make -f\n%:\n\tdh $@\n",
            "debian/source/format": "3.0 (native)\n",
            "Makefile": (
                ".PHONY: build/chan_rpt_fixture.so\n"
                "build/chan_rpt_fixture.so:\n"
                "\tdpkg-query -W librptadvschedule1 librptadvschedule-dev\n"
                "\tdpkg --compare-versions \"$$(dpkg-query -W -f='$${Version}' "
                'librptadvschedule1)" ge 0.1.0~alpha2-1\n'
                "\tdpkg --compare-versions \"$$(dpkg-query -W -f='$${Version}' "
                'librptadvschedule-dev)" ge 0.1.0~alpha2-1\n'
                "\tmkdir -p build\n\ttouch $@\n"
            ),
        }
        for filename, contents in sources.items():
            (production / filename).write_text(contents, encoding="utf-8", newline="\n")
        (production / "debian/rules").chmod(0o755)
        image_id = directory / "image-id"
        try:
            subprocess.run(
                [
                    "docker",
                    "buildx",
                    "build",
                    "--pull",
                    "--no-cache",
                    "--load",
                    "--progress=plain",
                    "--target=build",
                    "--iidfile",
                    str(image_id),
                    "--label=rpt_advanced.test=true",
                    "--label=org.rptadvanced.test.project=rpt_advanced-workflows",
                    f"--label=org.rptadvanced.test.scope={directory.name}",
                    "--build-context",
                    f"dependencies={packages}",
                    "--build-context",
                    f"production={production}",
                    "--file",
                    str(ROOT / "containers/test.Dockerfile"),
                    str(ROOT),
                ],
                check=True,
            )
        finally:
            if image_id.exists():
                subprocess.run(
                    ["docker", "image", "rm", image_id.read_text().strip()], check=True
                )
    print("Installed-image build dependency smoke passed")


if __name__ == "__main__":
    main()
