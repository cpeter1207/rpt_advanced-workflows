"""Resolve an immutable image index to explicit native manifest/config receipts."""

import argparse
import json
import re
import subprocess
from pathlib import Path

from phone_cohort import workflow_commit

REPOSITORY = "ghcr.io/cpeter1207/rpt-advanced-quality-debian13"
DIGEST = r"sha256:[0-9a-f]{64}"


def platform_descriptor(index, architecture):
    """Reject missing or ambiguous native platforms, including attestations."""
    matches = [item for item in index["manifests"]
               if item.get("platform", {}).get("os") == "linux"
               and item["platform"].get("architecture") == architecture]
    if architecture not in {"amd64", "arm64"} or len(matches) != 1:
        raise ValueError("one explicit native image manifest required")
    if not re.fullmatch(DIGEST, matches[0]["digest"]):
        raise ValueError("invalid platform manifest digest")
    return matches[0]


def image_receipt(index, architecture, descriptor, manifest, workflow):
    """Record registry-declared config ID, not an unobserved running-container ID."""
    receipt = {"index": index, "architecture": architecture,
               "platform_image": REPOSITORY + "@" + descriptor["digest"],
               "config_image_id": manifest["config"]["digest"],
               "workflow_commit": workflow,
               "evidence": "registry manifest/config identity; pinned job image"}
    validate_receipt(receipt, receipt["platform_image"], architecture, workflow)
    return receipt


def validate_receipt(receipt, image, architecture, workflow):
    """Bind each job to its architecture-specific image receipt."""
    if (not re.fullmatch(re.escape(REPOSITORY) + "@" + DIGEST, receipt["index"])
            or not re.fullmatch(re.escape(REPOSITORY) + "@" + DIGEST, image)
            or not re.fullmatch(DIGEST, receipt["config_image_id"])
            or receipt["platform_image"] != image or receipt["architecture"] != architecture
            or receipt["workflow_commit"] != workflow):
        raise ValueError("architecture-specific image provenance mismatch")


def load_receipt(root, image, architecture):
    receipt = json.loads((root / "image-receipts" / (architecture + ".json")).read_text())
    validate_receipt(receipt, image, architecture, workflow_commit())
    return receipt


def resolve(image, output):
    """Query manifests only; never pull image layers or execute foreign platforms."""
    if not re.fullmatch(re.escape(REPOSITORY) + "@" + DIGEST, image):
        raise ValueError("immutable quality index required")
    output.mkdir()
    def inspect(reference):
        raw = subprocess.check_output(["docker", "buildx", "imagetools", "inspect", "--raw", reference])
        return json.loads(raw)
    index = inspect(image)
    (output / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    for architecture in ("amd64", "arm64"):
        descriptor = platform_descriptor(index, architecture)
        child = REPOSITORY + "@" + descriptor["digest"]
        manifest = inspect(child)
        receipt = image_receipt(image, architecture, descriptor, manifest, workflow_commit())
        (output / (architecture + ".json")).write_text(json.dumps(receipt, indent=2) + "\n")
        (output / (architecture + "-manifest.json")).write_text(json.dumps(manifest, indent=2) + "\n")
        print(architecture + "=" + child)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    resolve(args.image, Path("image-receipts"))
