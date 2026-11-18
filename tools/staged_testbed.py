"""Build the existing RNNoise testbed only on a disposable hosted native runner."""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
from pathlib import Path

from phone_cohort import command, verify_source, workflow_commit
from staged_phone import PINS, sha256


def validate_host(environment, architecture, machine, free):
    """Never expose a development host socket or silently emulate ARM."""
    native = {"amd64": "x86_64", "arm64": "aarch64"}
    if (environment.get("GITHUB_ACTIONS") != "true"
            or environment.get("RUNNER_ENVIRONMENT") != "github-hosted"
            or native.get(architecture) != machine or free < 20 * 1024**3):
        raise ValueError("testbed requires a disk-safe native GitHub-hosted runner")


def build_arguments(architecture, image, source, receipt):
    """Reuse the pinned provider recipe, bind its base, and never tag or push."""
    if architecture not in {"amd64", "arm64"} or not re.fullmatch(
            r"ghcr.io/cpeter1207/rpt-advanced-quality-debian13@sha256:[0-9a-f]{64}", image):
        raise ValueError("native architecture and immutable quality base required")
    return ["docker", "build", "--platform", "linux/" + architecture,
            "--build-arg", "BASE_IMAGE=" + image, "--iidfile", str(receipt),
            "--file", str(Path(source) / "containers/quality.Dockerfile"), str(source)]


def execute(root, architecture, image):
    """Retain recipe/base/local image identity; this build alone qualifies nothing."""
    validate_host(os.environ, architecture, platform.machine(), shutil.disk_usage(root).free)
    source = root / "sources/rnnoise"
    verify_source(source, PINS["rnnoise"])
    output = root / "staged-output"
    output.mkdir(exist_ok=True)
    iid = output / "testbed-image-id"
    if iid.exists():
        raise ValueError("testbed receipt already exists")
    args = build_arguments(architecture, image, source, iid)
    subprocess.run(["docker", "pull", "--platform", "linux/" + architecture, image], check=True)
    base = json.loads(command(["docker", "image", "inspect", image]))
    if len(base) != 1 or base[0]["Architecture"] != architecture:
        raise ValueError("base image architecture mismatch")
    with (output / "testbed-build.log").open("w") as stream:
        subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT, check=True)
    identity = iid.read_text().strip()
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", identity):
        raise ValueError("invalid local testbed image identity")
    actual = json.loads(command(["docker", "image", "inspect", identity]))
    if len(actual) != 1 or actual[0]["Architecture"] != architecture:
        raise ValueError("testbed architecture mismatch")
    verify_source(source, PINS["rnnoise"])
    receipt = {"scope": "local hosted testbed only; tests pending", "architecture": architecture,
               "source_sha": PINS["rnnoise"], "workflow_commit": workflow_commit(),
               "recipe_sha256": sha256(source / "containers/quality.Dockerfile"),
               "base": image, "base_image_id": base[0]["Id"], "image_id": identity,
               "build_command": args}
    (output / "testbed.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(identity)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", required=True, choices=("amd64", "arm64"))
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    execute(Path.cwd().resolve(), args.arch, args.image)


if __name__ == "__main__":
    main()
