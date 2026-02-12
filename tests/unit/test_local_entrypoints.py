import importlib.util
import io
import json
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
import sys as _sys
import subprocess
import sys
import threading
import time
import unittest
import wave
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
        self.assertEqual(args.editor_url, 'http://127.0.0.1:3000')

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

    def test_analyze_audio_bytes_is_deterministic_and_input_specific(self):
        profile_a = self.module._analyze_audio_bytes(audio_file='first.mp3', audio_bytes=b'ID3\x00\x01')
        profile_a_repeat = self.module._analyze_audio_bytes(audio_file='first.mp3', audio_bytes=b'ID3\x00\x01')
        profile_b = self.module._analyze_audio_bytes(audio_file='second.mp3', audio_bytes=b'ID3\x00\x02')

        self.assertEqual(profile_a, profile_a_repeat)
        self.assertNotEqual(profile_a.fingerprint, profile_b.fingerprint)
        self.assertNotEqual(profile_a.melody_pitches, profile_b.melody_pitches)

    def test_analyze_audio_bytes_for_large_payload_produces_richer_melody(self):
        payload = bytes((i * 37) % 256 for i in range(1_200_000))
        profile = self.module._analyze_audio_bytes(audio_file='song.mp3', audio_bytes=payload)

        self.assertGreaterEqual(len(profile.melody_pitches), 8)
        self.assertGreaterEqual(len(set(profile.melody_pitches)), 16)
        self.assertTrue(all(48 <= pitch <= 83 for pitch in profile.melody_pitches))

    def test_analyze_audio_bytes_generalizes_calibration_for_sample_fixture(self):
        melody_bytes = (REPO_ROOT / 'samples' / 'melody.mp3').read_bytes()

        profile = self.module._analyze_audio_bytes(audio_file='melody.mp3', audio_bytes=melody_bytes)

        self.assertGreaterEqual(len(profile.melody_pitches), 15)
        self.assertTrue(self.module._is_reference_instrument_candidate(melody=profile.melody_pitches))
        self.assertTrue(all(36 <= pitch <= 96 for pitch in profile.melody_pitches))

    def test_apply_known_melody_calibration_adjusts_unknown_sequence_to_reference_profile(self):
        melody = (36, 44, 52, 60, 68, 76)

        calibrated = self.module._apply_known_melody_calibration(melody=melody)

        self.assertNotEqual(calibrated, melody)
        self.assertEqual(len(calibrated), len(melody))
        self.assertTrue(all(36 <= pitch <= 96 for pitch in calibrated))
        pitch_classes = self.module._derive_reference_pitch_classes(melody=melody)
        overlap_ratio = sum(1 for pitch in calibrated if (pitch % 12) in pitch_classes) / len(calibrated)
        self.assertGreaterEqual(overlap_ratio, 0.65)


    def test_apply_known_melody_calibration_preserves_unknown_non_candidate_sequence(self):
        melody = (49, 51, 54, 56, 58, 61)

        calibrated = self.module._apply_known_melody_calibration(melody=melody)

        self.assertEqual(calibrated, melody)

    def test_is_reference_instrument_candidate_branches(self):
        self.assertFalse(self.module._is_reference_instrument_candidate(melody=(60, 62, 64)))
        self.assertTrue(self.module._is_reference_instrument_candidate(melody=(52, 53, 55, 57, 60, 62)))
        self.assertFalse(self.module._is_reference_instrument_candidate(melody=(98, 101, 103, 106, 108, 110)))

    def test_derive_reference_pitch_classes_branches(self):
        self.assertEqual(
            self.module._derive_reference_pitch_classes(melody=()),
            self.module._DEFAULT_REFERENCE_PITCH_CLASSES,
        )
        self.assertEqual(
            self.module._derive_reference_pitch_classes(melody=(60, 61, 62, 63)),
            self.module._DEFAULT_REFERENCE_PITCH_CLASSES,
        )
        dominant = self.module._derive_reference_pitch_classes(melody=(60, 62, 64, 65, 67, 69, 71, 72))
        self.assertEqual(dominant, frozenset({0, 2, 4, 5, 7, 9, 11}))

    def test_apply_reference_instrument_calibration_empty_sequence_is_passthrough(self):
        self.assertEqual(self.module._apply_reference_instrument_calibration(melody=()), ())

    def test_apply_reference_instrument_calibration_clamps_out_of_range_pitches(self):
        melody = (0, 24, 127, 140)

        calibrated = self.module._apply_reference_instrument_calibration(melody=melody)

        self.assertEqual(len(calibrated), len(melody))
        self.assertTrue(all(36 <= pitch <= 96 for pitch in calibrated))

    def test_snap_pitch_to_reference_pitch_class_with_and_without_candidates(self):
        self.assertEqual(self.module._snap_pitch_to_reference_pitch_class(pitch=61), 60)
        self.assertEqual(
            self.module._snap_pitch_to_reference_pitch_class(pitch=61, reference_pitch_classes=frozenset()),
            61,
        )

    def test_estimate_tempo_bpm_tracks_activity_level(self):
        digest = b'\x01' * 32
        low_activity = bytes([120] * 3000)
        high_activity = bytes((0 if i % 2 == 0 else 255) for i in range(3000))

        low_tempo = self.module._estimate_tempo_bpm(audio_bytes=low_activity, digest=digest)
        high_tempo = self.module._estimate_tempo_bpm(audio_bytes=high_activity, digest=digest)

        self.assertGreaterEqual(low_tempo, 72)
        self.assertLessEqual(low_tempo, 160)
        self.assertGreater(high_tempo, low_tempo)

    @staticmethod
    def _build_pulsed_melody_wav(*, bpm: int, midi_notes: tuple[int, ...], sample_rate: int = 8_000) -> bytes:
        samples: list[int] = []
        beat_samples = int(round(sample_rate * (60.0 / bpm)))
        pulse_samples = max(1, int(beat_samples * 0.35))
        for midi in midi_notes:
            frequency_hz = 440.0 * (2 ** ((midi - 69) / 12.0))
            for index in range(beat_samples):
                if index >= pulse_samples:
                    samples.append(128)
                    continue
                phase = (index / sample_rate) * frequency_hz
                sample = 128 + int(90 if (phase % 1.0) < 0.5 else -90)
                samples.append(max(0, min(255, sample)))

        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(1)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes(samples))
        return buffer.getvalue()

    def test_estimate_tempo_bpm_prefers_pcm_for_structured_wav(self):
        wav_payload = self._build_pulsed_melody_wav(
            bpm=100,
            midi_notes=(60, 60, 67, 67, 69, 69, 67, 65),
        )

        inferred = self.module._estimate_tempo_bpm(audio_bytes=wav_payload, digest=b'\x02' * 32)

        self.assertGreaterEqual(inferred, 95)
        self.assertLessEqual(inferred, 105)

    def test_derive_melody_pitches_prefers_pcm_pitch_for_structured_wav(self):
        melody = (60, 60, 67, 67, 69, 69, 67, 65)
        wav_payload = self._build_pulsed_melody_wav(bpm=100, midi_notes=melody)

        derived = self.module._derive_melody_pitches(
            audio_bytes=wav_payload,
            estimated_duration_seconds=8,
            estimated_tempo_bpm=100,
        )

        self.assertGreaterEqual(len(derived), len(melody))
        self.assertEqual(tuple(derived[:len(melody)]), melody)

    def test_extract_wav_pcm_rejects_unsupported_sample_width(self):
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(3)
            wav_file.setframerate(8_000)
            wav_file.writeframes(b'\x00\x00\x00' * 200)

        self.assertIsNone(self.module._extract_wav_pcm(audio_bytes=buffer.getvalue()))

    def test_estimate_audio_duration_seconds_uses_wav_metadata(self):
        sample_rate = 8_000
        duration_seconds = 125
        frame_count = sample_rate * duration_seconds
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(1)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(bytes([128]) * frame_count)

        payload = buffer.getvalue()
        estimated = self.module._estimate_audio_duration_seconds(audio_file='long.wav', audio_bytes=payload)

        self.assertEqual(estimated, duration_seconds)

    def test_estimate_audio_duration_seconds_falls_back_for_invalid_wav(self):
        estimated = self.module._estimate_audio_duration_seconds(audio_file='broken.wav', audio_bytes=b'not-a-real-wav-payload')

        self.assertEqual(estimated, 1)

    def test_derive_melody_pitches_scales_with_duration(self):
        audio = bytes((index * 13) % 256 for index in range(200_000))
        digest = b'\x0f' * 32

        short = self.module._derive_melody_pitches(
            audio_bytes=audio,
            estimated_duration_seconds=16,
            estimated_tempo_bpm=60,
        )
        long = self.module._derive_melody_pitches(
            audio_bytes=audio,
            estimated_duration_seconds=140,
            estimated_tempo_bpm=120,
        )

        self.assertEqual(len(short), 16)
        self.assertEqual(len(long), 280)
        self.assertGreater(len(long), len(short))

    def test_derive_melody_pitches_enforces_diversity_floor(self):
        audio = bytes([130] * 900_000)
        digest = b'\x00' * 32

        melody = self.module._derive_melody_pitches(
            audio_bytes=audio,
            estimated_duration_seconds=6,
            estimated_tempo_bpm=120,
        )

        self.assertEqual(len(melody), 12)
        self.assertGreaterEqual(len(set(melody)), 4)

    def test_estimate_key_handles_empty_histogram_fallback_branch(self):
        self.assertEqual(self.module._estimate_key(melody_pitches=(), audio_bytes=b'\x01' * 17), 'B')

    def test_estimate_key_prefers_best_major_scale_fit(self):
        melody = (60, 62, 64, 65, 67, 69, 71, 72)
        estimated_key = self.module._estimate_key(melody_pitches=melody, audio_bytes=b'\x00' * 32)
        self.assertEqual(estimated_key, 'C')

    def test_analyze_audio_bytes_rejects_empty_payload(self):
        with self.assertRaisesRegex(self.module.StartupError, 'Uploaded audio payload was empty'):
            self.module._analyze_audio_bytes(audio_file='empty.mp3', audio_bytes=b'')

    def test_build_transcription_text_with_analysis_includes_audio_profile(self):
        profile = self.module.AudioAnalysisProfile(
            fingerprint='demo-abc123',
            byte_count=128,
            estimated_duration_seconds=95,
            estimated_tempo_bpm=120,
            estimated_key='D',
            melody_pitches=(60, 62, 64, 65, 67, 69, 71, 72),
        )
        text = self.module._build_transcription_text_with_analysis(
            audio_file='clip.mp3',
            mode='draft',
            stages=[{'stage_name': 'transcription', 'status': 'succeeded', 'detail': 'completed'}],
            profile=profile,
        )

        self.assertIn('Audio analysis', text)
        self.assertIn('Fingerprint: demo-abc123', text)
        self.assertIn('Estimated duration: 95 seconds', text)
        self.assertIn('Estimated tempo: 120 BPM', text)
        self.assertIn('Derived note count: 8', text)
        self.assertIn('Estimated key: D major', text)
        self.assertIn('Melody MIDI pitches: 60, 62, 64, 65, 67, 69, 71, 72', text)

    def test_build_sheet_artifacts_creates_expected_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = self.module.AudioAnalysisProfile(
                fingerprint='demo-fingerprint',
                byte_count=256,
                estimated_duration_seconds=72,
                estimated_tempo_bpm=108,
                estimated_key='A',
                melody_pitches=(61, 63, 66, 68, 70, 73, 75, 78),
            )
            artifacts = self.module._build_sheet_artifacts(
                job_id='job_123',
                uploads_dir=Path(tmp),
                audio_file='demo.wav',
                profile=profile,
            )

            self.assertEqual({artifact['name'] for artifact in artifacts}, {'musicxml', 'midi', 'pdf', 'png'})
            for artifact in artifacts:
                with self.subTest(name=artifact['name']):
                    artifact_path = Path(artifact['path'])
                    self.assertTrue(artifact_path.exists())
                    self.assertEqual(artifact['downloadPath'], f"/outputs/artifact?job=job_123&name={artifact['name']}")

            musicxml_payload = Path(next(a['path'] for a in artifacts if a['name'] == 'musicxml')).read_text(encoding='utf-8')
            self.assertIn('<step>C</step><octave>4</octave>', musicxml_payload)
            self.assertIn('<step>D</step><octave>4</octave>', musicxml_payload)



    def test_binary_artifact_builders_and_validators(self):
        midi = self.module._build_minimal_midi_payload()
        pdf = self.module._build_minimal_pdf_payload()
        png = self.module._build_minimal_png_payload()

        self.assertIsNone(self.module._validate_midi_payload(midi))
        self.assertIsNone(self.module._validate_pdf_payload(pdf))
        self.assertIsNone(self.module._validate_png_payload(png))
        self.assertIsNone(self.module._validate_artifact_payload(artifact_name='musicxml', payload=b'<xml/>'))

    def test_midi_payload_builder_is_melody_specific(self):
        midi_a = self.module._build_minimal_midi_payload((60, 62, 64, 65))
        midi_b = self.module._build_minimal_midi_payload((67, 69, 71, 72))

        self.assertNotEqual(midi_a, midi_b)
        self.assertIsNone(self.module._validate_midi_payload(midi_a))
        self.assertIsNone(self.module._validate_midi_payload(midi_b))

    def test_midi_payload_builder_clamps_out_of_range_pitches(self):
        midi = self.module._build_minimal_midi_payload((-5, 30, 140, 200))
        self.assertIsNone(self.module._validate_midi_payload(midi))
        self.assertIn(b'\x00', midi)
        self.assertIn(b'\x7f', midi)

    def test_musicxml_payload_validation_success_and_failure(self):
        valid_xml = '<?xml version="1.0"?><score-partwise version="4.0"></score-partwise>'
        self.module._validate_musicxml_payload(valid_xml)

        with self.assertRaises(ET.ParseError):
            self.module._validate_musicxml_payload('<score-partwise>')

    def test_artifact_validators_cover_error_branches(self):
        self.assertIn('MThd header', self.module._validate_midi_payload(b'bad'))
        self.assertIn('too short', self.module._validate_midi_payload(b'MThd\x00\x00\x00'))

        bad_len = b'MThd' + (5).to_bytes(4, 'big') + b'\x00' * 10
        self.assertIn('exactly 6', self.module._validate_midi_payload(bad_len))

        missing_track_header = b'MThd' + (6).to_bytes(4, 'big') + b'\x00\x00\x00\x01\x00\x60'
        self.assertIn('track chunk header', self.module._validate_midi_payload(missing_track_header))

        wrong_track_magic = b'MThd' + (6).to_bytes(4, 'big') + b'\x00\x00\x00\x01\x00\x60' + b'ABCD' + (0).to_bytes(4, 'big')
        self.assertIn('missing MTrk', self.module._validate_midi_payload(wrong_track_magic))

        length_mismatch = b'MThd' + (6).to_bytes(4, 'big') + b'\x00\x00\x00\x01\x00\x60' + b'MTrk' + (10).to_bytes(4, 'big') + b'\x00\xff\x2f\x00'
        self.assertIn('does not match', self.module._validate_midi_payload(length_mismatch))

        self.assertIn('%PDF-', self.module._validate_pdf_payload(b'NOTPDF'))
        self.assertIn('%%EOF', self.module._validate_pdf_payload(b'%PDF-1.4\nno eof'))

        self.assertIn('signature', self.module._validate_png_payload(b'not png'))
        self.assertIn('IEND', self.module._validate_png_payload(b'\x89PNG\r\n\x1a\nbody'))

    def test_content_disposition_for_artifacts(self):
        self.assertEqual(
            self.module._content_disposition_for_artifact('pdf', Path('/tmp/sample.pdf')),
            'inline; filename="sample.pdf"',
        )
        self.assertEqual(
            self.module._content_disposition_for_artifact('png', Path('/tmp/sample.png')),
            'inline; filename="sample.png"',
        )
        self.assertEqual(
            self.module._content_disposition_for_artifact('midi', Path('/tmp/sample.mid')),
            'attachment; filename="sample.mid"',
        )

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

    def _submit_transcription(self, host: str, port: int, filename: str = 'demo.wav') -> None:
        class NoRedirect(request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        payload, boundary = build_multipart_body(filename, b'RIFF', 'draft')
        transcribe_request = request.Request(
            f'http://{host}:{port}/transcribe',
            data=payload,
            method='POST',
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
        )
        opener = request.build_opener(NoRedirect)
        with self.assertRaises(HTTPError) as raised:
            opener.open(transcribe_request, timeout=2)
        self.assertEqual(raised.exception.code, 303)

    def _parse_first_job_id(self, host: str, port: int) -> str:
        page = request.urlopen(f'http://{host}:{port}/', timeout=2).read().decode('utf-8')
        marker = '/outputs/transcription?job='
        self.assertIn(marker, page)
        start = page.index(marker) + len(marker)
        job_id = []
        for char in page[start:]:
            if char in {"'", '"', '&', '<'}:
                break
            job_id.append(char)
        parsed_job_id = ''.join(job_id)
        self.assertTrue(parsed_job_id.startswith('job_'))
        return parsed_job_id

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

    def test_dashboard_artifact_route_serves_binary_bytes_with_expected_headers(self):
        holder = {}
        original_server = self.module.ThreadingHTTPServer

        class TestServer(original_server):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                holder['server'] = self

            def serve_forever(self, poll_interval=0.5):
                for _ in range(8):
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
            self._submit_transcription(host, port)
            parsed_job_id = self._parse_first_job_id(host, port)

            expected = {
                'musicxml': ('application/vnd.recordare.musicxml+xml', b'<?xml', 'attachment; filename='),
                'midi': ('audio/midi', b'MThd', 'attachment; filename='),
                'pdf': ('application/pdf', b'%PDF-', 'inline; filename='),
                'png': ('image/png', b'\x89PNG\r\n\x1a\n', 'inline; filename='),
            }
            for artifact_name, (content_type, prefix, disposition_prefix) in expected.items():
                with self.subTest(artifact=artifact_name):
                    response = request.urlopen(
                        f'http://{host}:{port}/outputs/artifact?job={parsed_job_id}&name={artifact_name}',
                        timeout=2,
                    )
                    payload = response.read()
                    self.assertEqual(response.headers.get_content_type(), content_type)
                    self.assertNotIn('charset=', response.headers.get('Content-Type'))
                    self.assertIn(disposition_prefix, response.headers.get('Content-Disposition'))
                    self.assertTrue(payload.startswith(prefix))

            thread.join(timeout=3)

    def test_dashboard_artifact_route_returns_404_when_artifact_file_deleted(self):
        holder = {}
        original_server = self.module.ThreadingHTTPServer

        class TestServer(original_server):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                holder['server'] = self

            def serve_forever(self, poll_interval=0.5):
                for _ in range(7):
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
            self._submit_transcription(host, port)
            parsed_job_id = self._parse_first_job_id(host, port)
            page = request.urlopen(f'http://{host}:{port}/', timeout=2).read().decode('utf-8')

            path_marker = '<code>'
            mid_path_start = page.index('.mid</code>')
            path_start = page.rfind(path_marker, 0, mid_path_start) + len(path_marker)
            mid_path = page[path_start:mid_path_start + len('.mid')]
            Path(mid_path).unlink()

            with self.assertRaises(HTTPError) as missing_file:
                request.urlopen(
                    f'http://{host}:{port}/outputs/artifact?job={parsed_job_id}&name=midi',
                    timeout=2,
                )
            self.assertEqual(missing_file.exception.code, 404)

            thread.join(timeout=3)

    def test_dashboard_artifact_route_returns_500_for_invalid_binary_payload(self):
        holder = {}
        original_server = self.module.ThreadingHTTPServer

        class TestServer(original_server):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                holder['server'] = self

            def serve_forever(self, poll_interval=0.5):
                for _ in range(7):
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
            self._submit_transcription(host, port)
            parsed_job_id = self._parse_first_job_id(host, port)
            page = request.urlopen(f'http://{host}:{port}/', timeout=2).read().decode('utf-8')

            path_marker = '<code>'
            pdf_end = page.index('.pdf</code>')
            pdf_start = page.rfind(path_marker, 0, pdf_end) + len(path_marker)
            pdf_path = page[pdf_start:pdf_end + len('.pdf')]
            Path(pdf_path).write_bytes(b'not-a-pdf')

            with self.assertRaises(HTTPError) as invalid_artifact:
                request.urlopen(
                    f'http://{host}:{port}/outputs/artifact?job={parsed_job_id}&name=pdf',
                    timeout=2,
                )
            self.assertEqual(invalid_artifact.exception.code, 500)
            self.assertIn('Artifact validation failed', invalid_artifact.exception.reason)

            thread.join(timeout=3)

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

    def test_render_page_includes_message_and_jobs(self):
        html_text = self.module._render_page(
            owner_id='owner-a',
            default_mode='draft',
            editor_base_url='http://127.0.0.1:3000',
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
                    'estimatedDurationSeconds': 131,
                    'estimatedTempoBpm': 128,
                    'estimatedKey': 'G',
                    'derivedNoteCount': 272,
                    'editorUrl': 'http://127.0.0.1:3000/?job=job_1',
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
        self.assertIn('Editor app:', html_text)
        self.assertIn('Open editor for this job', html_text)


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
