"""Test the bounded upstream packaging adjustment without a native build."""
import tempfile
import unittest
from pathlib import Path

import staged_sofia as sofia

RULES = "#!/usr/bin/make -f\n\n%:\n\tdh $@ --with autoreconf\n\noverride_dh_auto_configure:\n\t./configure \\\n\t  --prefix=/usr \\\n\t  --with-pic \\\n\t  --disable-stun\n\noverride_dh_auto_test:\n"
DEV = "usr/include/*/*/*.h\nusr/include/*/*/*.h.in\nusr/lib/libsofia-sip-ua.a\nusr/lib/libsofia-sip-ua.so\nusr/lib/pkgconfig/sofia-sip-ua.pc\nusr/share/sofia-sip/msg_parser.awk\nusr/share/sofia-sip/tag_dll.awk\n"
GLIB = "usr/lib/libsofia-sip-ua-glib.a\nusr/lib/libsofia-sip-ua-glib.so\nusr/lib/pkgconfig/sofia-sip-ua-glib.pc\n"


class SofiaPackageTests(unittest.TestCase):
    def source(self, root):
        for name, text in [("debian/rules", RULES), ("debian/libsofia-sip-ua-dev.install", DEV), ("debian/libsofia-sip-ua-glib-dev.install", GLIB)]:
            path = root / name
            path.parent.mkdir(exist_ok=True)
            path.write_text(text)

    def test_preserves_original_dynamic_configuration_and_stun_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.source(root)
            receipt = sofia.adjust_packaging(root)
            rules = (root / "debian/rules").read_text()
            self.assertIn("--disable-static", rules)
            self.assertNotIn("--disable-stun", rules)
            self.assertNotIn("--disable-openssl", rules)
            self.assertEqual(set(receipt), set(sofia.ORIGINAL_HASHES))
            for name in ("debian/libsofia-sip-ua-dev.install", "debian/libsofia-sip-ua-glib-dev.install"):
                self.assertNotIn(".a\n", (root / name).read_text())
                self.assertIn(".so\n", (root / name).read_text())

    def test_rejects_drift_before_any_packaging_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.source(root)
            (root / "debian/libsofia-sip-ua-dev.install").write_text("changed")
            with self.assertRaises(ValueError):
                sofia.adjust_packaging(root)
            self.assertEqual((root / "debian/rules").read_text(), RULES)

    def test_real_upstream_tests_are_separate_from_debian_empty_override(self):
        self.assertIn(("make", "-j1", "check"), sofia.BUILD_COMMANDS)
        self.assertLess(sofia.BUILD_COMMANDS.index(("dpkg-buildpackage", "-us", "-uc", "-b")), sofia.BUILD_COMMANDS.index(("make", "-j1", "check")))
        self.assertFalse(any("-d" in command or "equivs-build" in command for command in sofia.BUILD_COMMANDS))


if __name__ == "__main__":
    unittest.main()
