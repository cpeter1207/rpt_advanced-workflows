"""Fail-closed identity checks for private staged phone qualification."""

import hashlib
import re
import subprocess
from pathlib import Path

from phone_cohort import validate_manifest, verify_elf

CONTROLLER = "bc46f631d8da28fd69b41e4e1c33c7e3410d163b"
PINS = {
    "controller": CONTROLLER,
    "sdk": "3bcd75465120b87fabdf25a2b2e8c4a0e808e842",
    "adapter": "8dbf88fa929940f74e7b918e339edef503cca7f6",
    "codec": "8596809c3ff8493d705bc2f65371e9f0b6e4fef2",
    "radio": "8c5b5b41bc054a98dc7d36a7f199089bdc82b3b3",
    "rnnoise": "b25f187d958c9866430bdf968c2b2bb579e5d667",
}


def validate_sources(manifest):
    """Require the reviewed cohort, not just syntactically valid commit names."""
    validate_manifest(manifest)
    if {role: item["sha"] for role, item in manifest.items()} != PINS:
        raise ValueError("unreviewed staged cohort source")


def merge_packages(baseline, candidates, architecture):
    """Replace by binary package identity, never by filename or version order."""
    if architecture not in {"amd64", "arm64"}:
        raise ValueError("unsupported native architecture")
    groups = []
    for items in (baseline, candidates):
        group = {}
        for item in items:
            name = item["package"]
            if name in group or item["arch"] not in {architecture, "all"}:
                raise ValueError("duplicate package or wrong architecture")
            group[name] = item
        groups.append(group)
    merged = groups[0] | groups[1]
    return [merged[name] for name in sorted(merged)]


def sha256(path):
    """Hash bytes in bounded memory, including large provider libraries."""
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_files(root, expected):
    """Compare selected package bytes with installed files without root escapes."""
    root = Path(root).resolve()
    for name, digest in expected.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("unsafe package path")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError(f"missing or escaped installed file: {name}")
        if sha256(path) != digest:
            raise ValueError(f"installed byte mismatch: {name}")
    return expected.copy()


def loaded_paths(log):
    """Read glibc successful initialization paths, not attempted search names."""
    return {
        Path(name)
        for name in re.findall(r"^\s*\d+:\s+calling init:\s+(/[^\n]+?)\s*$", log, re.MULTILINE)
    }


def verify_loaded(paths, expected):
    """Require every selected DSO and reject same-name alternate loaded bytes."""
    selected = {Path(name).resolve(): digest for name, digest in expected.items()}
    if len(selected) != len(expected):
        raise ValueError("ambiguous selected DSO paths")
    names = {Path(name).name.split(".so")[0] for name in expected}
    loaded = set()
    for path in paths:
        resolved = path.resolve()
        if path.name.split(".so")[0] in names and resolved not in selected:
            raise ValueError(f"candidate DSO loaded outside selected package: {path}")
        loaded.add(resolved)
    if not set(selected).issubset(loaded):
        raise ValueError("required candidate DSO was not observed loaded")
    for path, digest in selected.items():
        if not path.is_file() or sha256(path) != digest:
            raise ValueError(f"loaded byte mismatch: {path}")
    return expected.copy()


def validate_baseline(actual, expected):
    """Reject all baseline drift, including IAX and binary package selections."""
    if actual != expected:
        raise ValueError("controller baseline dependency manifest changed")


def select_packages(items, required, architecture):
    """Require exactly one native artifact for each requested binary package."""
    selected = merge_packages([], items, architecture)
    result = [item for item in selected if item["package"] in required]
    if {item["package"] for item in result} != set(required):
        raise ValueError("missing required package artifact")
    return result


def package_info(path):
    """Read binary metadata and hash the exact local Debian archive."""
    path = Path(path).resolve(strict=True)
    fields = subprocess.check_output(
        ["dpkg-deb", "--show", "--showformat=${Package}\\t${Version}\\t${Architecture}", str(path)],
        text=True,
    ).split("\t")
    if len(fields) != 3:
        raise ValueError("invalid Debian package metadata")
    name, version, architecture = fields
    return {"package": name, "version": version, "arch": architecture,
            "path": str(path), "sha256": sha256(path)}


def package_files(package, stage, architecture):
    """Extract a build-owned archive and inventory its headers and native ELF."""
    stage = Path(stage).resolve()
    stage.mkdir()
    subprocess.run(["dpkg-deb", "--extract", str(package), str(stage)], check=True)
    result = {}
    for path in sorted(stage.rglob("*")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if not resolved.is_relative_to(stage):
            raise ValueError("package symlink escapes extraction root")
        name = path.relative_to(stage).as_posix()
        with path.open("rb") as stream:
            elf = stream.read(4) == b"\x7fELF"
        if elf:
            verify_elf(path, architecture)
        if elf or name.startswith("usr/include/"):
            result[name] = sha256(path)
    return result
