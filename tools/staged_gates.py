"""Ordinary controller/provider gates for an exact installed package cohort."""

import argparse
import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

from phone_cohort import command, verify_source, workflow_commit
from staged_packages import ORDER, guard, install, installed_receipt, inventory
from staged_phone import PINS, merge_packages, select_packages, sha256, validate_baseline, validate_sources

SOFIA_PACKAGES = {"libsofia-sip-ua0", "libsofia-sip-ua-dev"}


def require_sofia_pair(packages):
    """Check actual package eligibility; versions alone never attest provenance."""
    selected = [item for item in packages if item["package"] in SOFIA_PACKAGES]
    if len(selected) != 2 or {item["package"] for item in selected} != SOFIA_PACKAGES:
        raise ValueError("actual Sofia runtime and development packages required")
    if len({item["version"] for item in selected}) != 1:
        raise ValueError("Sofia runtime/development package versions differ")
    for item in selected:
        if subprocess.run(["dpkg", "--compare-versions", item["version"], "ge", "1.13.19"],
                          check=False).returncode:
            raise ValueError("Sofia package is below the controller dependency floor")


def gate_plan(phase, architecture):
    """Use existing audited targets without publishing or running ARM coverage."""
    if architecture not in {"amd64", "arm64"}:
        raise ValueError("unsupported native architecture")
    if phase == "independent":
        if architecture != "amd64":
            raise ValueError("platform-independent gate must run once")
        return [(role, ("make", "quality")) for role in ORDER if role != "sdk"] + [
            ("sdk", ("make", "lint", "static-analysis", "docs")),
            ("controller", ("make", "quality")),
        ]
    if phase == "native":
        return [(role, ("make", "platform-verify")) for role in ORDER if role != "sdk"] + [
            # SDK platform-verify includes coverage, forbidden on arm64.
            ("sdk", ("make", "check")),
            ("sdk", ("make", "distcheck", "DISTCHECK_TEST_TARGET=")),
            ("controller", ("make", "platform-verify")),
            ("controller", ("env", "DEB_BUILD_OPTIONS=nocheck", "dpkg-buildpackage", "-us", "-uc", "-b")),
        ]
    if phase == "coverage":
        if architecture != "amd64":
            raise ValueError("production coverage is amd64-only")
        return [(role, ("make", "coverage")) for role in (*ORDER, "controller")]
    raise ValueError("unsupported gate phase")


def validate_prepared(receipt, architecture, image, workflow, baseline):
    """Require this workflow's exact native source/image artifact, not a stale run."""
    if (receipt["architecture"] != architecture or receipt["image"] != image
            or receipt["workflow_commit"] != workflow or receipt["baseline_sha256"] != baseline
            or {role: item["sha"] for role, item in receipt["sources"].items()} != PINS):
        raise ValueError("prepared artifact provenance mismatch")


def validate_testbed(receipt, architecture, image, identity, workflow, recipe):
    """Bind the socket-visible local image to the reviewed recipe and source."""
    if (receipt["architecture"] != architecture or receipt["base"] != image
            or receipt["image_id"] != identity or receipt["workflow_commit"] != workflow
            or receipt["source_sha"] != PINS["rnnoise"] or receipt["recipe_sha256"] != recipe):
        raise ValueError("native testbed provenance mismatch")


def restore(root, architecture, image):
    """Verify transported archive bytes and reinstall the exact prepared cohort."""
    output = root / "staged-output"
    receipt = json.loads((output / "prepared.json").read_text())
    validate_prepared(receipt, architecture, image, workflow_commit(),
                      sha256(root / "qualification/phone-staged-baseline.json"))
    manifest = json.loads((root / "qualification/phone-staged.json").read_text())
    validate_sources(manifest)
    if receipt["sources"] != manifest:
        raise ValueError("prepared repository identity differs")
    actual = inventory(output / "packages")
    expected = receipt["packages"]
    fields = ("package", "version", "arch", "sha256")
    def identity(items):
        return sorted(tuple(item[field] for field in fields) for item in items)
    if identity(actual) != identity(expected):
        raise ValueError("transported package set differs from prepared bytes")
    require_sofia_pair(actual)
    install(actual)
    installed = installed_receipt(actual, architecture)
    if installed["files_sha256"] != receipt["installed"]["files_sha256"]:
        raise ValueError("restored package headers or ELF differ")
    return actual, manifest


def execute(root, phase, architecture, image):
    """Run actual ordinary gates; never convert missing prerequisites to success."""
    guard(architecture)
    plan = gate_plan(phase, architecture)
    if "CARGO_ENCODED_RUSTFLAGS" in os.environ:
        raise ValueError("encoded Rust flags override warnings")
    if os.environ.get("RPTADV_SOFIA_PREFIX") or os.environ.get("SOFIA_PREFIX"):
        raise ValueError("ordinary package gates cannot use private Sofia prefixes")
    os.environ["RUSTFLAGS"] = (os.environ.get("RUSTFLAGS", "") + " -Dwarnings").strip()
    os.environ.update(CARGO_BUILD_JOBS="1", RUST_TEST_THREADS="1", CARGO_INCREMENTAL="0", MAKEFLAGS="-j1")
    packages, manifest = restore(root, architecture, image)
    sources = root / "sources"
    baseline = json.loads((root / "qualification/phone-staged-baseline.json").read_text())
    validate_baseline(json.loads((sources / "controller/.github/dependencies.json").read_text()), baseline)
    for role, item in manifest.items():
        verify_source(sources / role, item["sha"])
    output = root / "staged-output"
    logs = output / (phase + "-logs")
    logs.mkdir()
    results = []
    try:
        for index, (role, arguments) in enumerate(plan):
            guard(architecture)
            arguments = list(arguments)
            if role == "rnnoise" and phase == "native":
                testbed = os.environ["STAGED_TESTBED_IMAGE"]
                if not re.fullmatch(r"sha256:[0-9a-f]{64}", testbed):
                    raise ValueError("native local RNNoise testbed image ID required")
                validate_testbed(json.loads((output / "testbed.json").read_text()),
                                 architecture, image, testbed, workflow_commit(),
                                 sha256(sources / "rnnoise/containers/quality.Dockerfile"))
                observed = json.loads(command(["docker", "image", "inspect", testbed]))
                if len(observed) != 1 or observed[0]["Architecture"] != architecture:
                    raise ValueError("wrong native RNNoise testbed architecture")
                arguments.append("AUTOPKGTEST_TESTBED_IMAGE=" + testbed)
            log = logs / f"{index:02d}-{role}.log"
            with log.open("w") as stream:
                process = subprocess.Popen(arguments, cwd=sources / role, stdout=stream,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    returncode = process.wait(timeout=7200)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                    results.append({"role": role, "command": arguments, "timeout": True})
                    raise
            results.append({"role": role, "command": arguments, "returncode": returncode})
            if returncode:
                raise subprocess.CalledProcessError(returncode, arguments)
        for role, item in manifest.items():
            verify_source(sources / role, item["sha"])
        if phase == "native":
            required = set(re.findall(r"^Package: (.+)$", (sources / "controller/debian/control").read_text(), re.M))
            controller = select_packages(inventory(sources), required, architecture)
            for item in controller:
                target = output / "packages" / Path(item["path"]).name
                if target.exists():
                    raise ValueError("controller package destination already exists")
                shutil.copyfile(item["path"], target)
                item["path"] = str(target)
            packages = merge_packages(packages, controller, architecture)
            install(packages)
            installed = installed_receipt(packages, architecture)
            (output / "installed.json").write_text(json.dumps({
                "architecture": architecture, "image": image, "sources": manifest,
                "workflow_commit": workflow_commit(), "packages": packages,
                "installed": installed,
            }, indent=2) + "\n")
            from installed_phone import execute as installed_tests
            installed_tests(root, architecture)
    finally:
        (output / (phase + "-commands.json")).write_text(json.dumps(results, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("independent", "native", "coverage"))
    parser.add_argument("--arch", required=True, choices=("amd64", "arm64"))
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    execute(Path.cwd().resolve(), args.phase, args.arch, args.image)


if __name__ == "__main__":
    main()
