import importlib.util
import json
from pathlib import Path
import sys as _sys
import subprocess
import sys
import threading
import time
import unittest
from unittest import mock
from urllib import request
from urllib.error import HTTPError


REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT_PATH = REPO_ROOT / 'infrastructure' / 'local-dev' / 'start_transcriberator.py'


def load_entrypoint_module():
    spec = importlib.util.spec_from_file_location('start_transcriberator', ENTRYPOINT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    _sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def build_multipart_body(filename: str, file_bytes: bytes, mode: str):
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    lines = [
        f'--{boundary}',
        'Content-Disposition: form-data; name="audio"; filename="' + filename + '"',
        'Content-Type: application/octet-stream',
        '',
        file_bytes.decode('latin-1'),
        f'--{boundary}',
        'Content-Disposition: form-data; name="mode"',
        '',
        mode,
        f'--{boundary}--',
        '',
    ]
    body = '\r\n'.join(lines).encode('latin-1')
    return body, boundary


def build_edit_body(job_id: str, transcription_text: str) -> bytes:
    from urllib.parse import urlencode

    return urlencode({'job_id': job_id, 'transcription_text': transcription_text}).encode('utf-8')


class TestStartupEntrypointRuntime(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_entrypoint_module()

    def test_parse_fail_stages_strips_empty_values(self):
        parsed = self.module._parse_fail_stages([' source_separation ', '', 'transcription'])
        self.assertEqual(parsed, {'source_separation', 'transcription'})

    def test_validate_mode_and_audio_filename(self):
        self.assertEqual(self.module._validate_mode('HQ'), 'hq')
        self.assertEqual(self.module._validate_audio_filename('clip.wav'), 'clip.wav')

    def test_validate_mode_rejects_invalid_value(self):
        with self.assertRaises(self.module.StartupError):
            self.module._validate_mode('turbo')

    def test_validate_audio_filename_rejects_invalid_values(self):
        for invalid in ['', 'track.txt']:
            with self.subTest(value=invalid):
                with self.assertRaises(self.module.StartupError):
                    self.module._validate_audio_filename(invalid)

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

    def test_build_arg_parser_defaults(self):
        parser = self.module.build_arg_parser()
        args = parser.parse_args([])
        self.assertEqual(args.mode, 'draft')
        self.assertEqual(args.owner_id, 'local-owner')
        self.assertFalse(args.no_hq_degradation)
        self.assertFalse(args.smoke_run)
        self.assertEqual(args.port, 4173)

    def test_main_smoke_success_and_error_paths(self):
        self.assertEqual(self.module.main(['--smoke-run', '--json']), 0)
        self.assertEqual(
            self.module.main([
                '--smoke-run',
                '--mode',
                'hq',
                '--fail-stage',
                'source_separation',
                '--no-hq-degradation',
            ]),
            2,
        )

    def test_main_server_path_invokes_dashboard(self):
        with mock.patch.object(self.module, 'serve_dashboard') as serve_dashboard:
            self.assertEqual(self.module.main(['--mode', 'hq', '--host', '0.0.0.0', '--port', '5123']), 0)

        serve_dashboard.assert_called_once()
        config = serve_dashboard.call_args.kwargs['config']
        self.assertEqual(config.mode, 'hq')
        self.assertEqual(config.host, '0.0.0.0')
        self.assertEqual(config.port, 5123)

    def test_format_summary_includes_stage_rows(self):
        summary = self.module.run_startup(mode='draft', owner_id='owner-a', project_name='Summary')
        text = self.module._format_summary(summary)
        self.assertIn('[entrypoint] stage timeline:', text)
        self.assertIn('decode_normalize', text)

    def test_build_transcription_text_includes_pipeline_details(self):
        text = self.module._build_transcription_text(
            audio_file='clip.wav',
            mode='hq',
            stages=[
                {'stage_name': 'decode_normalize', 'status': 'succeeded', 'detail': 'completed'},
                {'stage_name': 'transcription', 'status': 'succeeded', 'detail': 'completed'},
            ],
        )
        self.assertIn('Transcription draft for clip.wav', text)
        self.assertIn('- decode_normalize: succeeded (completed)', text)
        self.assertIn('Edit this text directly', text)

    def test_build_sheet_artifacts_creates_expected_outputs(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            artifacts = self.module._build_sheet_artifacts(
                job_id='job_123',
                uploads_dir=Path(tmp),
                audio_file='demo.wav',
            )

            self.assertEqual({artifact['name'] for artifact in artifacts}, {'musicxml', 'midi', 'pdf', 'png'})
            for artifact in artifacts:
                with self.subTest(name=artifact['name']):
                    artifact_path = Path(artifact['path'])
                    self.assertTrue(artifact_path.exists())
                    self.assertEqual(artifact['downloadPath'], f"/outputs/artifact?job=job_123&name={artifact['name']}")

    def test_augment_transcription_with_artifacts_appends_manifest(self):
        output = self.module._augment_transcription_with_artifacts(
            transcription_text='base content',
            artifacts=[
                {'name': 'musicxml', 'path': '/tmp/job.musicxml'},
                {'name': 'pdf', 'path': '/tmp/job.pdf'},
            ],
        )

        self.assertIn('base content', output)
        self.assertIn('Generated sheet music artifacts', output)
        self.assertIn('- musicxml: /tmp/job.musicxml', output)
        self.assertIn('- pdf: /tmp/job.pdf', output)


class TestDashboardServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_entrypoint_module()

    def test_dashboard_serves_ui_and_processes_transcription_submission(self):
        holder = {}
        original_server = self.module.ThreadingHTTPServer

        class TestServer(original_server):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                holder['server'] = self

            def serve_forever(self, poll_interval=0.5):
                self.handle_request()
                self.handle_request()

        with mock.patch.object(self.module, 'ThreadingHTTPServer', TestServer):
            thread = threading.Thread(
                target=self.module.serve_dashboard,
                kwargs={
                    'config': self.module.DashboardServerConfig(
                        host='127.0.0.1',
                        port=0,
                        owner_id='owner-a',
                        mode='draft',
                        allow_hq_degradation=True,
                    )
                },
                daemon=True,
            )
            thread.start()

            for _ in range(20):
                if 'server' in holder:
                    break
                time.sleep(0.05)
            self.assertIn('server', holder)

            host, port = holder['server'].server_address
            get_response = request.urlopen(f'http://{host}:{port}/', timeout=2)
            get_body = get_response.read().decode('utf-8')
            self.assertIn('Transcriberator Dashboard', get_body)

            class NoRedirect(request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            payload, boundary = build_multipart_body('demo.wav', b'RIFF', 'draft')
            post_request = request.Request(
                f'http://{host}:{port}/transcribe',
                data=payload,
                method='POST',
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
            )
            opener = request.build_opener(NoRedirect)
            with self.assertRaises(HTTPError) as raised:
                opener.open(post_request, timeout=2)
            self.assertEqual(raised.exception.code, 303)
            self.assertIn('/?msg=', raised.exception.headers['Location'])

            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_dashboard_can_view_and_edit_transcription_output(self):
        holder = {}
        original_server = self.module.ThreadingHTTPServer

        class TestServer(original_server):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                holder['server'] = self

            def serve_forever(self, poll_interval=0.5):
                for _ in range(5):
                    self.handle_request()

        with mock.patch.object(self.module, 'ThreadingHTTPServer', TestServer):
            thread = threading.Thread(
                target=self.module.serve_dashboard,
                kwargs={
                    'config': self.module.DashboardServerConfig(
                        host='127.0.0.1',
                        port=0,
                        owner_id='owner-a',
                        mode='draft',
                        allow_hq_degradation=True,
                    )
                },
                daemon=True,
            )
            thread.start()

            for _ in range(20):
                if 'server' in holder:
                    break
                time.sleep(0.05)
            self.assertIn('server', holder)

            host, port = holder['server'].server_address

            class NoRedirect(request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            payload, boundary = build_multipart_body('demo.wav', b'RIFF', 'draft')
            transcribe_request = request.Request(
                f'http://{host}:{port}/transcribe',
                data=payload,
                method='POST',
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
            )
            opener = request.build_opener(NoRedirect)
            with self.assertRaises(HTTPError):
                opener.open(transcribe_request, timeout=2)

            page = request.urlopen(f'http://{host}:{port}/', timeout=2).read().decode('utf-8')
            marker = '/outputs/transcription?job='
            self.assertIn(marker, page)
            start = page.index(marker) + len(marker)
            job_id = []
            for char in page[start:]:
                if char in {'\'', '"', '&', '<'}:
                    break
                job_id.append(char)
            parsed_job_id = ''.join(job_id)
            self.assertTrue(parsed_job_id.startswith('job_'))

            output_text = request.urlopen(
                f'http://{host}:{port}/outputs/transcription?job={parsed_job_id}',
                timeout=2,
            ).read().decode('utf-8')
            self.assertIn('Transcription draft for demo.wav', output_text)
            self.assertIn('Generated sheet music artifacts', output_text)

            edit_request = request.Request(
                f'http://{host}:{port}/edit-transcription',
                data=build_edit_body(parsed_job_id, 'custom edit v2'),
                method='POST',
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
            with self.assertRaises(HTTPError) as edit_raised:
                opener.open(edit_request, timeout=2)
            self.assertEqual(edit_raised.exception.code, 303)

            updated_text = request.urlopen(
                f'http://{host}:{port}/outputs/transcription?job={parsed_job_id}',
                timeout=2,
            ).read().decode('utf-8')
            self.assertEqual(updated_text, 'custom edit v2')

            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_dashboard_transcription_output_route_returns_404_for_unknown_job(self):
        holder = {}
        original_server = self.module.ThreadingHTTPServer

        class TestServer(original_server):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                holder['server'] = self

            def serve_forever(self, poll_interval=0.5):
                self.handle_request()

        with mock.patch.object(self.module, 'ThreadingHTTPServer', TestServer):
            thread = threading.Thread(
                target=self.module.serve_dashboard,
                kwargs={
                    'config': self.module.DashboardServerConfig(
                        host='127.0.0.1',
                        port=0,
                        owner_id='owner-a',
                        mode='draft',
                        allow_hq_degradation=True,
                    )
                },
                daemon=True,
            )
            thread.start()
            for _ in range(20):
                if 'server' in holder:
                    break
                time.sleep(0.05)
            self.assertIn('server', holder)

            host, port = holder['server'].server_address
            with self.assertRaises(HTTPError) as raised:
                request.urlopen(f'http://{host}:{port}/outputs/transcription?job=missing', timeout=2)
            self.assertEqual(raised.exception.code, 404)

            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_dashboard_artifact_route_serves_artifact_and_404_paths(self):
        holder = {}
        original_server = self.module.ThreadingHTTPServer

        class TestServer(original_server):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                holder['server'] = self

            def serve_forever(self, poll_interval=0.5):
                for _ in range(5):
                    self.handle_request()

        with mock.patch.object(self.module, 'ThreadingHTTPServer', TestServer):
            thread = threading.Thread(
                target=self.module.serve_dashboard,
                kwargs={
                    'config': self.module.DashboardServerConfig(
                        host='127.0.0.1',
                        port=0,
                        owner_id='owner-a',
                        mode='draft',
                        allow_hq_degradation=True,
                    )
                },
                daemon=True,
            )
            thread.start()

            for _ in range(20):
                if 'server' in holder:
                    break
                time.sleep(0.05)
            self.assertIn('server', holder)

            host, port = holder['server'].server_address

            class NoRedirect(request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None

            payload, boundary = build_multipart_body('demo.wav', b'RIFF', 'draft')
            transcribe_request = request.Request(
                f'http://{host}:{port}/transcribe',
                data=payload,
                method='POST',
                headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
            )
            opener = request.build_opener(NoRedirect)
            with self.assertRaises(HTTPError):
                opener.open(transcribe_request, timeout=2)

            page = request.urlopen(f'http://{host}:{port}/', timeout=2).read().decode('utf-8')
            marker = '/outputs/transcription?job='
            start = page.index(marker) + len(marker)
            job_id_chars = []
            for char in page[start:]:
                if char in {'\'', '"', '&', '<'}:
                    break
                job_id_chars.append(char)
            parsed_job_id = ''.join(job_id_chars)

            artifact_body = request.urlopen(
                f'http://{host}:{port}/outputs/artifact?job={parsed_job_id}&name=musicxml',
                timeout=2,
            ).read().decode('utf-8')
            self.assertIn('<score-partwise version="4.0">', artifact_body)

            with self.assertRaises(HTTPError) as missing_artifact:
                request.urlopen(
                    f'http://{host}:{port}/outputs/artifact?job={parsed_job_id}&name=missing',
                    timeout=2,
                )
            self.assertEqual(missing_artifact.exception.code, 404)

            with self.assertRaises(HTTPError) as missing_job:
                request.urlopen(f'http://{host}:{port}/outputs/artifact?job=missing&name=musicxml', timeout=2)
            self.assertEqual(missing_job.exception.code, 404)

            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_dashboard_edit_transcription_returns_404_for_unknown_job(self):
        holder = {}
        original_server = self.module.ThreadingHTTPServer

        class TestServer(original_server):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                holder['server'] = self

            def serve_forever(self, poll_interval=0.5):
                self.handle_request()

        with mock.patch.object(self.module, 'ThreadingHTTPServer', TestServer):
            thread = threading.Thread(
                target=self.module.serve_dashboard,
                kwargs={
                    'config': self.module.DashboardServerConfig(
                        host='127.0.0.1',
                        port=0,
                        owner_id='owner-a',
                        mode='draft',
                        allow_hq_degradation=True,
                    )
                },
                daemon=True,
            )
            thread.start()
            for _ in range(20):
                if 'server' in holder:
                    break
                time.sleep(0.05)
            self.assertIn('server', holder)

            host, port = holder['server'].server_address
            edit_request = request.Request(
                f'http://{host}:{port}/edit-transcription',
                data=build_edit_body('job_missing', 'data'),
                method='POST',
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
            with self.assertRaises(HTTPError) as raised:
                request.urlopen(edit_request, timeout=2)
            self.assertEqual(raised.exception.code, 404)

            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())

    def test_render_page_includes_message_and_jobs(self):
        html_text = self.module._render_page(
            owner_id='owner-a',
            default_mode='draft',
            message='done',
            jobs=[
                {
                    'audioFile': 'clip.wav',
                    'jobId': 'job_1',
                    'mode': 'draft',
                    'finalStatus': 'succeeded',
                    'submittedAtUtc': '2020-01-01T00:00:00+00:00',
                    'transcriptionPath': '/tmp/job_1_transcription.txt',
                    'transcriptionText': 'hello world',
                    'sheetArtifacts': [
                        {
                            'name': 'musicxml',
                            'path': '/tmp/job_1_demo.musicxml',
                            'downloadPath': '/outputs/artifact?job=job_1&name=musicxml',
                        }
                    ],
                    'stages': [{'stage_name': 'decode_normalize', 'status': 'succeeded', 'detail': 'completed'}],
                }
            ],
        )
        self.assertIn('Transcriberator Dashboard', html_text)
        self.assertIn('clip.wav', html_text)
        self.assertIn('done', html_text)
        self.assertIn('/outputs/transcription?job=job_1', html_text)
        self.assertIn('/outputs/artifact?job=job_1&amp;name=musicxml', html_text)
        self.assertIn('hello world', html_text)


class TestStartupEntrypointCli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(ENTRYPOINT_PATH), *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_smoke_human_output(self):
        result = self.run_cli('--smoke-run')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn('startup smoke run succeeded', result.stdout)

    def test_cli_json_output(self):
        result = self.run_cli('--smoke-run', '--json', '--mode', 'hq')
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload['mode'], 'hq')
        self.assertIn('stages', payload)

    def test_cli_returns_error_exit_code_for_failed_startup(self):
        result = self.run_cli('--smoke-run', '--mode', 'hq', '--fail-stage', 'source_separation', '--no-hq-degradation')
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


if __name__ == '__main__':
    unittest.main()
