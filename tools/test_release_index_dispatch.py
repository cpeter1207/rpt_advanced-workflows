#!/usr/bin/env python3
"""Keep successful controller releases connected to the signed package index."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseIndexDispatch(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/release.yml").read_text()

    def test_dispatch_token_is_an_optional_reusable_workflow_secret(self):
        interface = self.workflow.split("permissions:", 1)[0]
        self.assertRegex(
            interface,
            r"(?m)^    secrets:\n      APT_INDEX_DISPATCH_TOKEN:\n        required: false$",
        )

    def test_only_a_successful_publication_notifies_the_index(self):
        publish = self.workflow.split("\n  publish:\n", 1)[1]
        self.assertIn("INDEX_TOKEN: ${{ secrets.APT_INDEX_DISPATCH_TOKEN }}", publish)
        steps = re.split(r"(?m)^      - ", publish)[1:]
        release = next(i for i, step in enumerate(steps) if "gh release create" in step)
        dispatch = [
            (i, step)
            for i, step in enumerate(steps)
            if "USBRadioPlus-Workflows/actions/dispatch-package-index@main" in step
        ]
        self.assertEqual(len(dispatch), 1)
        index, step = dispatch[0]
        self.assertGreater(index, release)
        for contract in [
            "if: ${{ env.INDEX_TOKEN != '' }}",
            "package-repository: cpeter1207/rpt_advanced",
            "package-tag: ${{ inputs.tag }}",
            "token: ${{ secrets.APT_INDEX_DISPATCH_TOKEN }}",
        ]:
            self.assertIn(contract, step)
        self.assertNotIn("always()", step)

    def test_absent_token_leaves_the_release_published_with_a_clear_notice(self):
        publish = self.workflow.split("\n  publish:\n", 1)[1]
        self.assertIn("if: ${{ env.INDEX_TOKEN == '' }}", publish)
        self.assertIn("::notice::APT_INDEX_DISPATCH_TOKEN was not supplied", publish)


if __name__ == "__main__":
    unittest.main()
