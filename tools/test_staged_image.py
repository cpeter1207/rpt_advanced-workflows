"""Architecture-specific image provenance contracts, without registry access."""
import copy
import unittest

from staged_image import image_receipt, platform_descriptor, validate_receipt


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.repository = 'ghcr.io/cpeter1207/rpt-advanced-quality-debian13'
        self.index = self.repository + '@sha256:' + '1' * 64
        self.descriptor = {'digest': 'sha256:' + '2' * 64,
                           'platform': {'os': 'linux', 'architecture': 'arm64'}}
        self.manifest = {'config': {'digest': 'sha256:' + '3' * 64}}

    def test_select_exact_native_platform(self):
        index = {'manifests': [self.descriptor, {'digest': 'sha256:' + '4' * 64,
                                               'platform': {'os': 'unknown', 'architecture': 'unknown'}}]}
        self.assertEqual(platform_descriptor(index, 'arm64'), self.descriptor)
        with self.assertRaises(ValueError):
            platform_descriptor(index, 'amd64')
        index['manifests'].append(copy.deepcopy(self.descriptor))
        with self.assertRaises(ValueError):
            platform_descriptor(index, 'arm64')

    def test_receipt_binds_index_platform_config_and_workflow(self):
        receipt = image_receipt(self.index, 'arm64', self.descriptor, self.manifest, 'a' * 40)
        child = self.repository + '@' + self.descriptor['digest']
        validate_receipt(receipt, child, 'arm64', 'a' * 40)
        self.assertEqual(receipt['config_image_id'], self.manifest['config']['digest'])
        for field in ('architecture', 'platform_image', 'workflow_commit', 'config_image_id'):
            bad = dict(receipt)
            bad[field] = 'wrong'
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_receipt(bad, child, 'arm64', 'a' * 40)


if __name__ == '__main__':
    unittest.main()
