"""Ordinary controller/provider gates for an exact installed package cohort."""

import subprocess

from staged_packages import ORDER

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
