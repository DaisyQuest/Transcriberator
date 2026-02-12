import unittest
from pathlib import Path
import re


class TestScaffoldGovernance(unittest.TestCase):
    def test_agents_contains_required_workflow_items(self):
        text = Path('AGENTS.md').read_text(encoding='utf-8')
        required = [
            'Read `Final_Spec.md` at the start of every task.',
            "read that module's `$ModuleName_Spec.md` first.",
            'check `additional_tasks/` within that module',
            'Run all tests before committing.',
            'create `$taskslug_work_description.md` in `/workdescriptions`',
            'check off the relevant checkbox in `Work_Checklist.md`',
        ]
        for item in required:
            with self.subTest(item=item):
                self.assertIn(item, text)

    def test_each_module_has_additional_tasks_directory(self):
        module_paths = [
            Path('modules/dashboard-api'),
            Path('modules/dashboard-ui'),
            Path('modules/editor-app'),
            Path('modules/orchestrator'),
            Path('modules/worker-audio'),
            Path('modules/worker-separation'),
            Path('modules/worker-transcription'),
            Path('modules/worker-quantization'),
            Path('modules/worker-engraving'),
            Path('modules/shared-contracts'),
        ]
        for module in module_paths:
            with self.subTest(module=str(module)):
                extra = module / 'additional_tasks'
                self.assertTrue(extra.is_dir(), f"Missing {extra}")
                self.assertTrue((extra / 'README.md').is_file(), f"Missing {extra / 'README.md'}")

    def test_work_checklist_contains_checked_task(self):
        text = Path('Work_Checklist.md').read_text(encoding='utf-8')
        self.assertIn('## Task Completion Checkboxes', text)
        self.assertRegex(text, r'- \[x\] WC-TASK-001:')

    def test_final_spec_identifiers_are_unique(self):
        text = Path('Final_Spec.md').read_text(encoding='utf-8')
        ids = re.findall(r'^## (FS-\d{3}) ', text, flags=re.MULTILINE)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 68)


if __name__ == '__main__':
    unittest.main()


class TestDevelopmentTaskPlan(unittest.TestCase):
    def test_development_tasks_file_exists_with_key_sections(self):
        text = Path('Development_Tasks.md').read_text(encoding='utf-8')
        required_sections = [
            '# Development_Tasks.md',
            '## Phase 0 — Foundation Setup (Serial, No Parallelism)',
            '## Phase 1 — Shared Contracts and Interfaces (Serial by Design)',
            '## Phase 2 — Module Skeletons Against Frozen Contracts (Parallelizable)',
            '## Conflict-Avoidance Matrix (Delegation Cheat Sheet)',
            '## File Partitioning Convention for Parallel Test Work',
        ]
        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, text)

    def test_shared_contract_tasks_precede_parallel_module_tasks(self):
        text = Path('Development_Tasks.md').read_text(encoding='utf-8')
        dt006 = text.find('### DT-006 Orchestrator stage-state contract')
        dt007 = text.find('#### DT-007 Dashboard API skeleton')
        dt010 = text.find('#### DT-010 Orchestrator runtime skeleton')
        self.assertGreaterEqual(dt006, 0)
        self.assertGreaterEqual(dt007, 0)
        self.assertGreaterEqual(dt010, 0)
        self.assertLess(dt006, dt007)
        self.assertLess(dt006, dt010)

    def test_parallel_tracks_and_conflict_matrix_cover_modules(self):
        text = Path('Development_Tasks.md').read_text(encoding='utf-8')
        indicators = [
            '### Parallel Track A (User-facing web)',
            '### Parallel Track B (Pipeline core)',
            '### Parallel Track C (Environment enablement)',
            '| `modules/shared-contracts/` |',
            '| `modules/dashboard-api/` |',
            '| `modules/worker-*/` |',
        ]
        for marker in indicators:
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_work_checklist_has_new_checked_task(self):
        text = Path('Work_Checklist.md').read_text(encoding='utf-8')
        self.assertRegex(
            text,
            r'- \[x\] WC-TASK-002: Create `Development_Tasks\.md` with serial-first shared-contract planning and conflict-minimizing delegation guidance\.',
        )

    def test_workdescription_exists_for_task(self):
        path = Path('workdescriptions/development-task-plan_work_description.md')
        self.assertTrue(path.is_file())
        content = path.read_text(encoding='utf-8')
        for item in ['## Summary', '## Work Performed', '## Validation']:
            with self.subTest(item=item):
                self.assertIn(item, content)
