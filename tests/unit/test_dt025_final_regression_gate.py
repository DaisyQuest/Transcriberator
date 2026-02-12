import re
import unittest
from pathlib import Path


class TestDT025ReleaseGateArtifacts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release_path = Path('docs/release/DT-025_Final_Regression_Coverage_Gate.md')
        cls.release_text = cls.release_path.read_text(encoding='utf-8')

    def test_release_doc_exists_with_required_sections(self):
        self.assertTrue(self.release_path.is_file())
        required_sections = [
            '# DT-025 Final Regression and Branch Coverage Gate',
            '## Scope',
            '## Validation Evidence Map',
            '## Release Gate Execution Order',
            '## Commands',
            '## Sign-off Checklist',
        ]
        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, self.release_text)

    def test_scope_matches_dt025_owner_and_exit_criteria(self):
        snippets = [
            'Dependency baseline: DT-024 must be complete.',
            'Owner scope: `tests/`, CI configs.',
            'Full suite green.',
            'Branch coverage report meets policy target (>=95%).',
            'Windows local runbook validated end-to-end.',
        ]
        for snippet in snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, self.release_text)

    def test_release_doc_references_dependency_and_user_guides(self):
        for artifact in [
            'workdescriptions/dt-024-milestone-acceptance-gate-checks_work_description.md',
            'docs/runbooks/DT-016_Local_Dev_Windows_Runbook.md',
            'userguide.md',
            'userguide.html',
        ]:
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, self.release_text)
                self.assertTrue(Path(artifact).is_file())


class TestDT025CoverageAndCiPolicy(unittest.TestCase):
    def test_coveragerc_enforces_branch_and_fail_under(self):
        text = Path('.coveragerc').read_text(encoding='utf-8')
        self.assertIn('branch = True', text)
        self.assertIn('fail_under = 95', text)

    def test_pytest_ini_uses_importlib_mode(self):
        text = Path('pytest.ini').read_text(encoding='utf-8')
        self.assertIn('--import-mode=importlib', text)

    def test_ci_workflow_executes_coverage_threshold_gate(self):
        path = Path('.github/workflows/ci.yml')
        self.assertTrue(path.is_file())
        text = path.read_text(encoding='utf-8')
        self.assertIn('pytest --cov=. --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=95', text)
        self.assertRegex(text, r'python-version:\s*[\'\"]3\.10[\'\"]')


class TestDT025UserGuideAndWindowsReadiness(unittest.TestCase):
    def test_userguide_markdown_contains_windows_and_coverage_commands(self):
        text = Path('userguide.md').read_text(encoding='utf-8')
        self.assertIn('## Windows Local Runbook Alignment', text)
        self.assertIn('py -m pytest --cov=. --cov-branch --cov-report=term-missing --cov-fail-under=95', text)

    def test_userguide_html_accessibility_and_navigation_landmarks(self):
        text = Path('userguide.html').read_text(encoding='utf-8')
        required_markup = [
            '<a class="skip-link" href="#main-content">Skip to main content</a>',
            '<nav aria-label="Table of contents">',
            '<main id="main-content">',
            'id="windows"',
            'id="troubleshooting"',
            'py -m pytest --cov=. --cov-branch --cov-report=term-missing --cov-fail-under=95',
        ]
        for snippet in required_markup:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, text)

    def test_docs_and_tests_readmes_link_dt025_assets(self):
        docs_text = Path('docs/README.md').read_text(encoding='utf-8')
        tests_text = Path('tests/README.md').read_text(encoding='utf-8')

        self.assertIn('DT-025_Final_Regression_Coverage_Gate.md', docs_text)
        self.assertIn('userguide.md', docs_text)
        self.assertIn('userguide.html', docs_text)

        self.assertIn('## Pytest Regression Gate (DT-025)', tests_text)
        self.assertIn('--cov-fail-under=95', tests_text)


class TestDT025ChecklistStatus(unittest.TestCase):
    def test_dt025_work_description_and_checklist_entry_exist(self):
        description = Path('workdescriptions/dt-025-final-regression-and-branch-coverage-gate_work_description.md')
        self.assertTrue(description.is_file())
        for heading in ['## Summary', '## Work Performed', '## Validation']:
            with self.subTest(heading=heading):
                self.assertIn(heading, description.read_text(encoding='utf-8'))

        checklist = Path('Work_Checklist.md').read_text(encoding='utf-8')
        self.assertRegex(checklist, r'- \[x\] WC-TASK-010: Complete DT-025 final regression and branch coverage gate')


if __name__ == '__main__':
    unittest.main()
