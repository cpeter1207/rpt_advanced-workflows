"""Check installed-image runtime selection without building production."""

import tempfile
import unittest
from pathlib import Path

from stage_test_image_packages import PACKAGES, select_packages, stage_packages


class PackageSelectionTests(unittest.TestCase):
    def fixture(self, product="librptadv-product3"):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for name in (*PACKAGES, product):
            (root / f"{name}_0.1.0~alpha25-1_arm64.deb").touch()
        return root

    def test_supported_runtime_versions_and_exact_count(self):
        for version in (2, 3):
            with self.subTest(version=version):
                root = self.fixture(f"librptadv-product{version}")
                for unrelated in (
                    "librptadv-product-dev",
                    "librptadv-product3-dbgsym",
                    "librptadv-product3extra",
                    "unrelated",
                ):
                    (root / f"{unrelated}_1_arm64.deb").touch()
                selected = select_packages(root)
                self.assertEqual(len(selected), 9)
                destination = root / "staged"
                stage_packages(root, destination)
                self.assertEqual(
                    sorted(p.name for p in destination.iterdir()),
                    sorted(p.name for p in selected),
                )

    def test_missing_runtime_rejected(self):
        root = self.fixture()
        next(root.glob("librptadv-product3_*.deb")).unlink()
        with self.assertRaises(ValueError):
            select_packages(root)

    def test_multiple_runtime_versions_rejected(self):
        root = self.fixture()
        (root / "librptadv-product2_1_arm64.deb").touch()
        with self.assertRaises(ValueError):
            select_packages(root)

    def test_duplicate_package_architecture_rejected(self):
        root = self.fixture()
        (root / "rpt-advanced_1_amd64.deb").touch()
        with self.assertRaises(ValueError):
            select_packages(root)

    def test_missing_adapter_fails_before_copy(self):
        root = self.fixture()
        next(root.glob("librptadv-jitter-adapter1_*.deb")).unlink()
        destination = root / "staged"
        with self.assertRaises(ValueError):
            stage_packages(root, destination)
        self.assertFalse(destination.exists())

    def test_dockerfile_uses_validated_staging(self):
        dockerfile = Path(__file__).resolve().parents[1] / "containers/test.Dockerfile"
        text = dockerfile.read_text()
        self.assertIn(
            "python3 /tmp/stage_test_image_packages.py / /test-packages", text
        )
        self.assertIn(
            "COPY --from=runtime-packages /test-packages/ /tmp/packages/", text
        )
        self.assertNotIn("/librptadv-product2_*.deb", text)


if __name__ == "__main__":
    unittest.main()
