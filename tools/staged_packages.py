"""Build-only private Debian candidate packages inside guarded native CI jobs."""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from phone_cohort import (
    REPOSITORIES,
    command,
    dependencies,
    verify_source,
    workflow_commit,
)
from staged_image import load_receipt
from staged_phone import (
    merge_packages,
    package_files,
    package_info,
    select_packages,
    sha256,
    validate_baseline,
    validate_sources,
    verify_files,
)

ORDER = ("rnnoise", "codec", "radio", "adapter", "sdk")


def required_packages(role, baseline):
    """Select only declared binary outputs; never install the SDK channel driver."""
    if role == "sdk":
        return {"libusbradioplus-product1", "libusbradioplus-product-dev"}
    if role == "rnnoise":
        return {"librptadv-rnnoise-adapter1", "librptadv-rnnoise-adapter-dev"}
    if role not in ORDER:
        raise ValueError("unsupported candidate package role")
    repository = REPOSITORIES[role].split("/")[1]
    matches = [entry for entry in baseline if entry["repository"] == repository]
    if len(matches) != 1:
        raise ValueError("ambiguous baseline package selection")
    return set(matches[0]["packages"])


def validate_guard(environment, expected, actual, debian):
    """Refuse host use and emulation before any install or build command."""
    if (
        environment.get("GITHUB_ACTIONS") != "true"
        or environment.get("STAGED_PHONE_DISPOSABLE") != "1"
        or expected not in {"amd64", "arm64"}
        or expected != actual
        or debian != "13"
    ):
        raise ValueError("requires disposable native Debian 13 CI job")


def guard(architecture):
    """Require native CI plus disk reserve, never clean unrelated state."""
    release = dict(
        line.split("=", 1) for line in Path("/etc/os-release").read_text().splitlines()
        if "=" in line
    )
    validate_guard(os.environ, architecture, command(["dpkg", "--print-architecture"]),
                   release["VERSION_ID"].strip('"'))
    for path in (Path.cwd(), Path("/var")):
        if shutil.disk_usage(path).free < 12 * 1024**3:
            raise ValueError(f"insufficient guarded build disk: {path}")


def run(arguments, cwd=None):
    """Execute one audited command; its log belongs to the CI step."""
    print("+", " ".join(map(str, arguments)), flush=True)
    subprocess.run(list(map(str, arguments)), cwd=cwd, check=True)


def inventory(directory):
    """Read only top-level .debs; bootstrap artifacts are not final selections."""
    return [package_info(path) for path in sorted(Path(directory).glob("*.deb"))]


def install(items):
    """Explicit local archive paths force same-version candidate replacement."""
    if not items:
        raise ValueError("empty package installation")
    for item in items:
        if sha256(item["path"]) != item["sha256"]:
            raise ValueError("package bytes changed before installation")
    run(["apt-get", "install", "--reinstall", "-y", *[x["path"] for x in items]])
    run(["ldconfig"])


def installed_receipt(items, architecture):
    """Bind selected archive bytes to actual installed headers, ELF and loader paths."""
    expected = {}
    with tempfile.TemporaryDirectory(prefix="staged-phone-inventory-") as temporary:
        for index, item in enumerate(items):
            files = package_files(item["path"], Path(temporary) / str(index), architecture)
            for name, digest in files.items():
                if name in expected and expected[name] != digest:
                    raise ValueError("conflicting selected package file")
                expected[name] = digest
    verify_files(Path("/"), expected)
    resolved_candidates = {str(Path("/", name).resolve()): digest for name, digest in expected.items()}
    candidate_names = {Path(name).name.split(".so")[0] for name in expected if ".so" in name}
    elf = {}
    for name in expected:
        path = Path("/", name)
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                continue
        dynamic = command(["readelf", "-d", str(path)])
        if "(NEEDED)" not in dynamic:
            continue
        resolved = dependencies(command(["ldd", str(path)]))
        hashes = {}
        for library, target in resolved.items():
            actual = str(Path(target).resolve())
            digest = sha256(target)
            if library.split(".so")[0] in candidate_names and resolved_candidates.get(actual) != digest:
                raise ValueError(f"candidate resolution escaped selected packages: {target}")
            hashes[actual] = digest
        elf[name] = {"dynamic": dynamic, "resolved_sha256": hashes}
    return {"files_sha256": expected, "elf": elf,
            "dpkg_status": command(["dpkg-query", "-W"])}


def prepare(root, architecture, image):
    """Build candidate archives, install them and retain a private exact package set."""
    guard(architecture)
    if not re.fullmatch(r"ghcr.io/cpeter1207/rpt-advanced-quality-debian13@sha256:[0-9a-f]{64}", image):
        raise ValueError("immutable quality image required")
    if "CARGO_ENCODED_RUSTFLAGS" in os.environ:
        raise ValueError("encoded Rust flags would override the warning policy")
    os.environ["RUSTFLAGS"] = (os.environ.get("RUSTFLAGS", "") + " -Dwarnings").strip()
    os.environ.update(CARGO_BUILD_JOBS="1", RUST_TEST_THREADS="1", CARGO_INCREMENTAL="0", MAKEFLAGS="-j1")
    manifest = json.loads((root / "qualification/phone-staged.json").read_text())
    validate_sources(manifest)
    baseline = json.loads((root / "qualification/phone-staged-baseline.json").read_text())
    sources = root / "sources"
    validate_baseline(json.loads((sources / "controller/.github/dependencies.json").read_text()), baseline)
    for role, entry in manifest.items():
        verify_source(sources / role, entry["sha"])
    image_identity = load_receipt(root, image, architecture)
    output = root / "staged-output"
    output.mkdir(exist_ok=True)
    destination = output / "packages"
    destination.mkdir()
    base_packages = inventory(root / "dependencies/packages")
    from staged_sofia import build_sofia

    candidates = build_sofia(root, architecture)
    for role in ORDER:
        guard(architecture)
        source = sources / role
        verify_source(source, manifest[role]["sha"])
        run(["mk-build-deps", "--install", "--remove", "--tool",
             "apt-get -y --no-install-recommends", "debian/control"], cwd=source)
        # Tests run in the later native gate; these archives remain unqualified.
        run(["env", "DEB_BUILD_OPTIONS=nocheck", "dpkg-buildpackage", "-us", "-uc", "-b"], cwd=source)
        selected = select_packages(inventory(sources), required_packages(role, baseline), architecture)
        for item in selected:
            copy = destination / Path(item["path"]).name
            if copy.exists():
                raise ValueError("candidate package filename collision")
            shutil.copyfile(item["path"], copy)
            item["path"] = str(copy)
        install(selected)
        verify_source(source, manifest[role]["sha"])
        candidates.extend(selected)
        # Catch package-manager dependency replacement of previous candidates.
        installed_receipt(candidates, architecture)
    final = merge_packages(base_packages, candidates, architecture)
    for item in final:
        target = destination / Path(item["path"]).name
        if Path(item["path"]) != target:
            if target.exists():
                raise ValueError("baseline/candidate filename collision")
            shutil.copyfile(item["path"], target)
        item["path"] = str(target)
    install(final)
    receipt = {
        "scope": "private preparation only; native/full gates pending; not a release",
        "architecture": architecture, "image": image, "image_identity": image_identity, "sources": manifest,
        "workflow_commit": workflow_commit(), "packages": final,
        "extra_prerequisites": json.loads((output / "sofia.json").read_text()),
        "baseline_sha256": sha256(root / "qualification/phone-staged-baseline.json"),
        "installed": installed_receipt(final, architecture),
    }
    (output / "prepared.json").write_text(json.dumps(receipt, indent=2) + "\n")


def main():
    """Expose only guarded private package preparation, with no publish operation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arch", required=True, choices=("amd64", "arm64"))
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    prepare(Path.cwd().resolve(), args.arch, args.image)


if __name__ == "__main__":
    main()
