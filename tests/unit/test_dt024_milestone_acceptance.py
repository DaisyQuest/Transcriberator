import re
import unittest
from pathlib import Path


class TestDT024MilestoneChecklistDocument(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = Path('docs/release/DT-024_Milestone_Acceptance_Checklist.md')
        cls.text = cls.path.read_text(encoding='utf-8')

    def test_release_checklist_exists_and_has_top_level_sections(self):
        self.assertTrue(self.path.is_file())
        required_sections = [
            '# DT-024 Milestone Acceptance Checklist (M0/M1/M2/M3)',
            '## Scope',
            '## Dependency Gate (DT-020..DT-023)',
            '## Milestone Gate Matrix',
            '## Release Readiness Execution Order',
            '## Commands',
        ]
        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, self.text)

    def test_scope_declares_owner_scope_and_dependency_baseline(self):
        expectations = [
            'Dependency baseline: DT-020, DT-021, DT-022, DT-023 must be complete.',
            'Owner scope: `docs/`, release checklists, `tests/`.',
            'Verification posture: deterministic repository checks + test suite execution + branch coverage gate.',
        ]
        for snippet in expectations:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, self.text)

    def test_dependency_gate_rows_reference_expected_workdescriptions_and_checklist(self):
        rows = [
            'workdescriptions/dt-020-observability-instrumentation-pass_work_description.md',
            'workdescriptions/dt-021_reliability-and-recovery-pass_work_description.md',
            'workdescriptions/dt-022-performance-and-ux-pass_work_description.md',
            'workdescriptions/dt-023-security-privacy-pass_work_description.md',
            'Work_Checklist.md',
        ]
        for expected_path in rows:
            with self.subTest(expected_path=expected_path):
                self.assertIn(expected_path, self.text)
                self.assertTrue(Path(expected_path).is_file())

    def test_milestone_sections_include_fs_alignment_and_required_artifacts(self):
        milestone_expectations = {
            '### M0 Gate (FS-060)': [
                'tests/integration/test_draft_pipeline.py',
                'modules/shared-contracts/schemas/v1/',
                'modules/editor-app/src/editor_app_skeleton.py',
                'modules/editor-app/tests/test_editor_app_skeleton.py',
            ],
            '### M1 Gate (FS-061)': [
                'modules/worker-quantization/worker_quantization_skeleton.py',
                'tests/integration/test_revision_exports.py',
            ],
            '### M2 Gate (FS-062)': [
                'modules/orchestrator/hq_pipeline_adapter.py',
                'modules/worker-separation/worker_separation_skeleton.py',
                'tests/integration/test_hq_pipeline.py',
                'tests/integration/test_recovery.py',
            ],
            '### M3 Gate (FS-063)': [
                'tests/integration/test_security.py',
                'tests/integration/test_observability.py',
                'python -m coverage run --branch -m unittest discover -s tests -t .',
            ],
        }

        for milestone_header, snippets in milestone_expectations.items():
            with self.subTest(milestone=milestone_header):
                self.assertIn(milestone_header, self.text)
                for snippet in snippets:
                    with self.subTest(milestone=milestone_header, snippet=snippet):
                        self.assertIn(snippet, self.text)

    def test_release_execution_order_is_explicitly_numbered(self):
        numbered_steps = re.findall(r'^\d+\. .+$', self.text, flags=re.MULTILINE)
        self.assertGreaterEqual(len(numbered_steps), 5)
        self.assertIn('1. Validate dependency gate (DT-020..DT-023 evidence).', numbered_steps)
        self.assertIn('3. Run branch coverage report and enforce >=95%.', numbered_steps)

    def test_commands_section_contains_expected_gates(self):
        expected_commands = [
            'python -m unittest discover -s tests -t .',
            'python -m coverage run --branch -m unittest discover -s tests -t .',
            'python -m coverage report -m',
        ]
        for command in expected_commands:
            with self.subTest(command=command):
                self.assertIn(command, self.text)


class TestDT024TrackingAndChecklistStatus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.work_checklist = Path('Work_Checklist.md').read_text(encoding='utf-8')

    def test_milestone_rows_marked_done(self):
        completed_rows = [
            '| WC-060 | FS-060 | Deliver M0 milestone package | DONE |',
            '| WC-061 | FS-061 | Deliver M1 milestone package | DONE |',
            '| WC-062 | FS-062 | Deliver M2 milestone package | DONE |',
            '| WC-063 | FS-063 | Deliver M3 milestone package | DONE |',
        ]
        for row in completed_rows:
            with self.subTest(row=row):
                self.assertIn(row, self.work_checklist)

    def test_dt024_completion_checkbox_exists_and_is_checked(self):
        self.assertIn('WC-TASK-009', self.work_checklist)
        self.assertRegex(
            self.work_checklist,
            r'- \[x\] WC-TASK-009: Complete DT-024 milestone acceptance',
        )

    def test_dt024_work_description_exists_with_standard_sections(self):
        path = Path('workdescriptions/dt-024-milestone-acceptance-gate-checks_work_description.md')
        self.assertTrue(path.is_file())
        text = path.read_text(encoding='utf-8')
        for heading in ['## Summary', '## Work Performed', '## Validation']:
            with self.subTest(heading=heading):
                self.assertIn(heading, text)

    def test_docs_readme_links_release_checklist(self):
        text = Path('docs/README.md').read_text(encoding='utf-8')
        self.assertIn('## Release', text)
        self.assertIn('release/DT-024_Milestone_Acceptance_Checklist.md', text)


if __name__ == '__main__':
    unittest.main()
