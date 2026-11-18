"""Structure contracts for manual-only staged native qualification."""
import unittest
from pathlib import Path

import yaml


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.workflow = yaml.safe_load((Path(__file__).resolve().parents[1] /
                                       '.github/workflows/phone-staged.yml').read_text())

    def test_exact_branch_only_read_only_publication_scope(self):
        trigger = self.workflow.get('on', self.workflow.get(True))
        self.assertEqual(trigger, {'push': {'branches': ['qualification/phone-staged-20261118']}})
        self.assertEqual(self.workflow['permissions'], {'contents': 'read'})
        check = next(step for step in self.workflow['jobs']['image']['steps'] if step.get('id') == 'check')
        self.assertEqual(check['env']['IMAGE'],
                         'ghcr.io/cpeter1207/rpt-advanced-quality-debian13@sha256:'
                         'c3800ed0094d0d01284b70481d3189a76044042b2900594115db2e2a41f2d0fa')

    def test_other_workflows_cannot_run_for_staged_branch_push(self):
        root = Path(__file__).resolve().parents[1]
        branch = 'qualification/phone-staged-20261118'
        for path in (root / '.github/workflows').glob('*.yml'):
            if path.name == 'phone-staged.yml':
                continue
            workflow = yaml.safe_load(path.read_text())
            trigger = workflow.get('on', workflow.get(True))
            if 'push' in trigger:
                push = trigger['push']
                self.assertIsInstance(push, dict, path.name)
                self.assertIn('branches', push, path.name)
                self.assertNotIn(branch, push['branches'], path.name)
                self.assertFalse(any('*' in value or '?' in value or value.startswith('!')
                                     for value in push['branches']), path.name)

    def test_architectures_and_order(self):
        jobs = self.workflow['jobs']
        for name in ('prepare', 'native'):
            matrix = jobs[name]['strategy']['matrix']['include']
            self.assertEqual({x['arch'] for x in matrix}, {'amd64', 'arm64'})
        self.assertIn('independent', jobs['native']['needs'])
        self.assertIn('independent', jobs['coverage']['needs'])
        self.assertNotIn('strategy', jobs['coverage'])
        self.assertNotIn('strategy', jobs['independent'])

    def test_each_job_uses_its_explicit_native_manifest_and_receipt(self):
        jobs = self.workflow['jobs']
        self.assertEqual(set(jobs['image']['outputs']), {'amd64', 'arm64'})
        for phase in ('prepare', 'independent', 'native', 'coverage'):
            key = 'matrix.arch' if phase in ('prepare', 'native') else "'amd64'"
            expected = '${{ needs.image.outputs[' + key + '] }}'
            self.assertEqual(jobs[phase]['container']['image'], expected)
            self.assertEqual(jobs[phase]['env']['QUALIFICATION_IMAGE'], expected)
            self.assertTrue(any(step.get('with', {}).get('name') == 'staged-image-receipts'
                                for step in jobs[phase]['steps']))

    def test_docker_socket_is_native_only(self):
        for name, job in self.workflow['jobs'].items():
            socket = '/var/run/docker.sock' in str(job)
            self.assertEqual(socket, name == 'native')

    def test_terminal_gate_requires_every_stage_success(self):
        gate = self.workflow['jobs']['qualified']
        self.assertEqual(set(gate['needs']), {'prepare', 'independent', 'native', 'coverage'})
        self.assertEqual(gate['if'], '${{ always() }}')
        self.assertIn('all(.[]; .result == "success")', str(gate['steps']))


if __name__ == '__main__':
    unittest.main()
