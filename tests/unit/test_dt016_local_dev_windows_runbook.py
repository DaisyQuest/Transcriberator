import unittest
from pathlib import Path


class TestDT016RunbookBaseline(unittest.TestCase):
    def test_runbook_exists_with_required_sections_and_commands(self):
        runbook = Path('docs/runbooks/DT-016_Local_Dev_Windows_Runbook.md')
        self.assertTrue(runbook.is_file())

        text = runbook.read_text(encoding='utf-8')
        required_snippets = [
            '# DT-016 Local Dev and Windows Runbook Baseline',
            '## Prerequisites',
            '### PowerShell (Windows)',
            '### Bash (macOS/Linux/Git Bash)',
            'python -m unittest discover -s tests -t .',
            'git config --global core.longpaths true',
            'git config --global core.autocrlf true',
            '## Troubleshooting Matrix',
            '## Definition of Done for DT-016',
        ]
        for snippet in required_snippets:
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, text)

    def test_docs_and_infrastructure_readmes_index_dt016_assets(self):
        docs_readme = Path('docs/README.md').read_text(encoding='utf-8')
        infra_readme = Path('infrastructure/README.md').read_text(encoding='utf-8')

        self.assertIn('runbooks/DT-016_Local_Dev_Windows_Runbook.md', docs_readme)
        for marker in [
            'local-dev/README.md',
            'local-dev/bootstrap.ps1',
            'local-dev/bootstrap.sh',
            'local-dev/env.example',
        ]:
            with self.subTest(marker=marker):
                self.assertIn(marker, infra_readme)


class TestDT016InfrastructureAssets(unittest.TestCase):
    def test_local_dev_directory_contains_expected_files(self):
        base = Path('infrastructure/local-dev')
        self.assertTrue(base.is_dir())

        expected = ['README.md', 'bootstrap.ps1', 'bootstrap.sh', 'env.example']
        for file_name in expected:
            with self.subTest(file_name=file_name):
                self.assertTrue((base / file_name).is_file())

    def test_bootstrap_scripts_are_observable_and_idempotent(self):
        ps1 = Path('infrastructure/local-dev/bootstrap.ps1').read_text(encoding='utf-8')
        sh = Path('infrastructure/local-dev/bootstrap.sh').read_text(encoding='utf-8')

        checks = [
            ('powershell status logging', '[dt-016] Starting local bootstrap', ps1),
            ('powershell venv branch', "if (-not (Test-Path '.venv'))", ps1),
            ('powershell python guard', 'python executable not found on PATH', ps1),
            ('bash status logging', '[dt-016] Starting local bootstrap', sh),
            ('bash venv branch', 'if [[ ! -d .venv ]]; then', sh),
            ('bash python guard', 'python executable not found on PATH', sh),
            ('bash strict mode', 'set -euo pipefail', sh),
        ]
        for title, snippet, text in checks:
            with self.subTest(title=title):
                self.assertIn(snippet, text)

    def test_environment_template_contains_observability_and_endpoint_placeholders(self):
        env_text = Path('infrastructure/local-dev/env.example').read_text(encoding='utf-8')
        for required_var in [
            'TRANSCRIBERATOR_ENV=local',
            'TRANSCRIBERATOR_API_BASE_URL=http://localhost:8000',
            'TRANSCRIBERATOR_STORAGE_ENDPOINT=http://localhost:10000',
            'TRANSCRIBERATOR_QUEUE_ENDPOINT=http://localhost:10001',
            'TRANSCRIBERATOR_LOG_LEVEL=DEBUG',
            'TRANSCRIBERATOR_TRACE_ENABLED=true',
        ]:
            with self.subTest(required_var=required_var):
                self.assertIn(required_var, env_text)


class TestDT016TaskTrackingArtifacts(unittest.TestCase):
    def test_work_description_exists_with_standard_sections(self):
        path = Path('workdescriptions/dt-016-local-dev-windows-runbook-baseline_work_description.md')
        self.assertTrue(path.is_file())
        content = path.read_text(encoding='utf-8')

        for heading in ['## Summary', '## Work Performed', '## Validation']:
            with self.subTest(heading=heading):
                self.assertIn(heading, content)

    def test_work_checklist_marks_dt016_task_complete(self):
        text = Path('Work_Checklist.md').read_text(encoding='utf-8')
        self.assertIn('WC-TASK-006', text)
        self.assertIn('DT-016', text)
        self.assertRegex(text, r'- \[x\] WC-TASK-006:')


if __name__ == '__main__':
    unittest.main()
