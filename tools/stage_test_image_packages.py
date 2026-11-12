"""Stage the exact runtime package set used by the installed test image."""

import re
import shutil
import sys
from pathlib import Path

PACKAGES = (
    "app-rpt-advanced",
    "rpt-advanced",
    "librptadv-file-adapter1",
    "librptadv-speech-adapter1",
    "librptadv-control-asterisk-adapter1",
    "librptadv-control-standalone-adapter1",
    "librptadv-resolver-adapter1",
    "librptadv-jitter-adapter1",
)


def select_packages(directory):
    """Require one artifact per runtime package, including one product SONAME."""
    artifacts = list(directory.glob("*.deb"))
    selected = []
    patterns = [re.escape(name) for name in PACKAGES] + [r"librptadv-product[0-9]+"]
    for package in patterns:
        matches = [
            path
            for path in artifacts
            if re.fullmatch(package + r"_[^_]+_[^_]+\.deb", path.name)
        ]
        if len(matches) != 1:
            raise ValueError(
                f"Expected exactly one {package} package, got {len(matches)}"
            )
        selected.extend(matches)
    return selected


def stage_packages(source, destination):
    """Validate the complete set before copying into a new staging directory."""
    selected = select_packages(source)
    destination.mkdir()
    for package in selected:
        shutil.copy2(package, destination / package.name)


if __name__ == "__main__":
    stage_packages(Path(sys.argv[1]), Path(sys.argv[2]))
