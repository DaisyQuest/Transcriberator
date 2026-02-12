import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT_PATH = REPO_ROOT / 'infrastructure' / 'local-dev' / 'start_transcriberator.py'


def load_entrypoint_module():
    spec = importlib.util.spec_from_file_location('start_transcriberator', ENTRYPOINT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class TestStartupEntrypointRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_entrypoint_module()

    def test_parse_fail_stages_strips_empty_values(self):
        parsed = self.module._parse_fail_stages([' source_separation ', '', 'transcription'])
        self.assertEqual(parsed, {'source_separation', 'transcription'})

    def test_run_startup_supports_draft_flow(self):
        summary = self.module.run_startup(mode='draft', owner_id='owner-a', project_name='Draft Smoke')
        self.assertEqual(summary['mode'], 'draft')
        self.assertEqual(summary['finalStatus'], 'succeeded')
        self.assertEqual(summary['stages'][1]['status'], 'skipped')

    def test_run_startup_supports_hq_degradation_when_separation_fails(self):
        summary = self.module.run_startup(
            mode='hq',
            owner_id='owner-a',
            project_name='HQ Smoke',
            fail_stages={'source_separation'},
            allow_hq_degradation=True,
        )
        self.assertEqual(summary['finalStatus'], 'succeeded')
        self.assertEqual(summary['stages'][1]['status'], 'skipped')
        self.assertIn('degraded', summary['stages'][1]['detail'])

    def test_run_startup_raises_on_failed_execution(self):
        with self.assertRaises(self.module.StartupError):
            self.module.run_startup(
                mode='hq',
                owner_id='owner-a',
                project_name='HQ Failure',
                fail_stages={'source_separation'},
                allow_hq_degradation=False,
            )

    def test_run_startup_rejects_invalid_mode(self):
        with self.assertRaises(self.module.StartupError):
            self.module.run_startup(mode='turbo', owner_id='owner-a', project_name='Invalid')


    def test_build_arg_parser_defaults(self):
        parser = self.module.build_arg_parser()
        args = parser.parse_args([])
        self.assertEqual(args.mode, 'draft')
        self.assertEqual(args.owner_id, 'local-owner')
        self.assertFalse(args.no_hq_degradation)

    def test_main_success_and_error_paths(self):
        self.assertEqual(self.module.main(['--json']), 0)
        self.assertEqual(
            self.module.main(['--mode', 'hq', '--fail-stage', 'source_separation', '--no-hq-degradation']),
            2,
        )

    def test_format_summary_includes_stage_rows(self):
        summary = self.module.run_startup(mode='draft', owner_id='owner-a', project_name='Summary')
        text = self.module._format_summary(summary)
        self.assertIn('[entrypoint] stage timeline:', text)
        self.assertIn('decode_normalize', text)


class TestStartupEntrypointCli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ENTRYPOINT_PATH), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_default_human_output(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('startup smoke run succeeded', result.stdout)

    def test_cli_json_output(self):
        result = self.run_cli('--json', '--mode', 'hq')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['mode'], 'hq')
        self.assertIn('stages', payload)

    def test_cli_returns_error_exit_code_for_failed_startup(self):
        result = self.run_cli('--mode', 'hq', '--fail-stage', 'source_separation', '--no-hq-degradation')
        self.assertEqual(result.returncode, 2)
        self.assertIn('[entrypoint] ERROR', result.stderr)


class TestEntrypointWrappersAndDocs(unittest.TestCase):
    def test_wrapper_scripts_exist_and_delegate_to_python_entrypoint(self):
        sh = (REPO_ROOT / 'start.sh').read_text(encoding='utf-8')
        ps1 = (REPO_ROOT / 'start.ps1').read_text(encoding='utf-8')

        self.assertIn('infrastructure/local-dev/start_transcriberator.py', sh)
        self.assertIn('set -euo pipefail', sh)
        self.assertIn('Launching Transcriberator', sh)

        self.assertIn('infrastructure/local-dev/start_transcriberator.py', ps1)
        self.assertIn("$ErrorActionPreference = 'Stop'", ps1)
        self.assertIn('Launching Transcriberator', ps1)

    def test_user_guides_document_standard_entrypoints(self):
        markdown = (REPO_ROOT / 'userguide.md').read_text(encoding='utf-8')
        html = (REPO_ROOT / 'userguide.html').read_text(encoding='utf-8')
        runbook = (REPO_ROOT / 'docs' / 'runbooks' / 'DT-016_Local_Dev_Windows_Runbook.md').read_text(encoding='utf-8')
        local_dev = (REPO_ROOT / 'infrastructure' / 'local-dev' / 'README.md').read_text(encoding='utf-8')

        for doc_text in [markdown, html, runbook, local_dev]:
            with self.subTest(document=doc_text[:40]):
                self.assertIn('start_transcriberator.py', doc_text)

        self.assertIn('./start.sh --mode draft', markdown)
        self.assertIn('.\\start.ps1 -mode hq', markdown)


if __name__ == '__main__':
    unittest.main()
