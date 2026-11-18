"""Build real upstream Sofia Debian packages with the prior tested features."""

import json
import os
import shutil
from pathlib import Path

from phone_cohort import command, verify_source
from staged_packages import guard, install, inventory, run
from staged_phone import select_packages, sha256

SOURCE = "6dce59d35535e6dd3945c7b0f76dbf1ba884202d"
REPOSITORY = "https://github.com/freeswitch/sofia-sip.git"
ORIGINAL_HASHES = {
    "debian/rules": "bf365ea7e86d4cc4044ef3e2071ec8a24ea6eca9ff7727ac7eee9ac33314e614",
    "debian/libsofia-sip-ua-dev.install": "aae5c4b04315ccf4c83f734cd8352ae7c1b7727b293cdad7e21f37686967a61e",
    "debian/libsofia-sip-ua-glib-dev.install": "bcfe3049833ca15649d79534b19c72bf7654215d5425dc4d6ef621d374e09bbf",
}
BUILD_COMMANDS = (
    ("mk-build-deps", "--install", "--remove", "--tool", "apt-get -y --no-install-recommends", "debian/control"),
    ("dpkg-buildpackage", "-us", "-uc", "-b"),
    # The upstream Debian rules deliberately leave dh_auto_test empty.
    ("make", "-j1", "check"),
)


def adjust_packaging(root):
    """Apply only hash-bound dynamic-only/STUN-preserving packaging changes."""
    for name, digest in ORIGINAL_HASHES.items():
        if sha256(root / name) != digest:
            raise ValueError(f"upstream packaging changed: {name}")
    result = {}
    for name, digest in ORIGINAL_HASHES.items():
        path = root / name
        original = path.read_text()
        if name == "debian/rules":
            updated = original.replace("--disable-stun", "--disable-static")
        else:
            updated = "".join(line for line in original.splitlines(keepends=True) if not line.rstrip().endswith(".a"))
        path.write_text(updated)
        result[name] = {"upstream_sha256": digest, "adjusted_sha256": sha256(path)}
    return result


def build_sofia(root, architecture):
    """Produce genuine packages; install only after upstream tests succeed."""
    guard(architecture)
    source = root / "sources/sofia"
    source.mkdir()
    run(["git", "init", "-q", str(source)])
    run(["git", "-C", str(source), "fetch", "--depth=1", REPOSITORY, SOURCE])
    run(["git", "-C", str(source), "checkout", "--detach", "FETCH_HEAD"])
    verify_source(source, SOURCE)
    if command(["dpkg-parsechangelog", "-S", "Version"], source) != "1.13.19-0":
        raise ValueError("unexpected upstream Sofia package version")
    packaging = adjust_packaging(source)
    previous = os.environ.get("CFLAGS")
    os.environ["CFLAGS"] = ((previous or "") + " -Werror").strip()
    try:
        for arguments in BUILD_COMMANDS:
            run(arguments, cwd=source)
    finally:
        if previous is None:
            os.environ.pop("CFLAGS", None)
        else:
            os.environ["CFLAGS"] = previous
    changed = set(command(["git", "diff", "--name-only"], source).splitlines())
    if changed != set(ORIGINAL_HASHES):
        raise ValueError("unexpected tracked Sofia build changes")
    for name, item in packaging.items():
        if sha256(source / name) != item["adjusted_sha256"]:
            raise ValueError("Sofia packaging changed during build")
    packages = select_packages(inventory(root / "sources"),
                               {"libsofia-sip-ua0", "libsofia-sip-ua-dev"}, architecture)
    destination = root / "staged-output/packages"
    for item in packages:
        if item["version"] != "1.13.19-0":
            raise ValueError("built Sofia package version differs from source")
        target = destination / Path(item["path"]).name
        if target.exists():
            raise ValueError("Sofia package output already exists")
        shutil.copyfile(item["path"], target)
        item["path"] = str(target)
    install(packages)
    receipt = {
        "scope": "additional private prerequisite, not original six-source cohort or a release",
        "repository": REPOSITORY, "source": SOURCE, "architecture": architecture,
        "packaging": packaging, "commands": BUILD_COMMANDS, "packages": packages,
        "tests": "make -j1 check completed successfully before installation",
    }
    (root / "staged-output/sofia.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return packages
