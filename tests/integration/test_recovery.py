import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


runtime_mod = load_module("orchestrator_runtime_recovery_test", "modules/orchestrator/runtime_skeleton.py")
hq_mod = load_module("hq_pipeline_recovery_test", "modules/orchestrator/hq_pipeline_adapter.py")
audio_mod = load_module("audio_worker_recovery_test", "modules/worker-audio/worker_audio_skeleton.py")
separation_mod = load_module("separation_worker_recovery_test", "modules/worker-separation/worker_separation_skeleton.py")
transcription_mod = load_module(
    "transcription_worker_recovery_test", "modules/worker-transcription/worker_transcription_skeleton.py"
)
quantization_mod = load_module(
    "quantization_worker_recovery_test", "modules/worker-quantization/worker_quantization_skeleton.py"
)
engraving_mod = load_module("engraving_worker_recovery_test", "modules/worker-engraving/worker_engraving_skeleton.py")


class TestOrchestratorRecoveryBehavior(unittest.TestCase):
    def setUp(self):
        self.runtime = runtime_mod.OrchestratorRuntime(
            now_provider=lambda: datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        )

    def test_hq_separation_failure_without_degrade_stops_pipeline(self):
        result = self.runtime.run_job(
            runtime_mod.OrchestratorJobRequest(job_id="hq-no-degrade", mode=runtime_mod.JobMode.HQ, allow_hq_degradation=False),
            fail_stages={"source_separation"},
        )

        self.assertEqual(result.final_status, runtime_mod.StageStatus.FAILED)
        self.assertEqual([record.stage_name for record in result.stage_records], ["decode_normalize", "source_separation"])
        self.assertEqual(result.stage_records[-1].detail, "simulated stage failure")

    def test_draft_mode_skip_precedes_failure_injection(self):
        result = self.runtime.run_job(
            runtime_mod.OrchestratorJobRequest(job_id="draft-skip", mode=runtime_mod.JobMode.DRAFT),
            fail_stages={"source_separation"},
        )

        separation_record = result.stage_records[1]
        self.assertEqual(separation_record.status, runtime_mod.StageStatus.SKIPPED)
        self.assertEqual(result.final_status, runtime_mod.StageStatus.SUCCEEDED)

    def test_failure_on_first_stage_short_circuits_remaining_stages(self):
        result = self.runtime.run_job(
            runtime_mod.OrchestratorJobRequest(job_id="fail-first", mode=runtime_mod.JobMode.HQ),
            fail_stages={"decode_normalize", "transcription", "engraving"},
        )

        self.assertEqual(result.final_status, runtime_mod.StageStatus.FAILED)
        self.assertEqual(len(result.stage_records), 1)
        self.assertEqual(result.stage_records[0].stage_name, "decode_normalize")

    def test_final_status_empty_record_set_resolves_to_skipped(self):
        empty = runtime_mod.OrchestratorJobResult(job_id="empty", mode=runtime_mod.JobMode.DRAFT, run_id="run-empty")
        self.assertEqual(empty.final_status, runtime_mod.StageStatus.SKIPPED)


class TestWorkerFailureAndRecoveryPaths(unittest.TestCase):
    def test_audio_worker_recovery_after_validation_error(self):
        worker = audio_mod.AudioWorker()

        with self.assertRaisesRegex(ValueError, "Unsupported audio format"):
            worker.process(audio_mod.AudioTaskRequest(asset_id="asset-a", source_uri="blob://a", audio_format="ogg"))

        recovered = worker.process(audio_mod.AudioTaskRequest(asset_id="asset-a", source_uri="blob://a", audio_format="mp3"))
        self.assertIn("normalized://asset-a-mp3-44100.pcm", recovered.normalized_uri)

    def test_separation_worker_timeout_then_recovery(self):
        worker = separation_mod.SeparationWorker()

        timed_out = worker.process(
            separation_mod.SeparationTaskRequest(
                asset_id="asset-sep", normalized_uri="normalized://asset-sep", simulate_timeout=True
            )
        )
        self.assertTrue(timed_out.degraded)

        recovered = worker.process(
            separation_mod.SeparationTaskRequest(
                asset_id="asset-sep", normalized_uri="normalized://asset-sep", target_stems=("vocals",)
            )
        )
        self.assertFalse(recovered.degraded)
        self.assertEqual(recovered.stem_uris["vocals"], "stem://asset-sep/vocals.wav")

    def test_transcription_worker_recovery_after_missing_model_version(self):
        worker = transcription_mod.TranscriptionWorker()

        with self.assertRaisesRegex(ValueError, "model_version is required"):
            worker.process(transcription_mod.TranscriptionTaskRequest(source_uri="normalized://x", polyphonic=True, model_version=""))

        recovered = worker.process(
            transcription_mod.TranscriptionTaskRequest(source_uri="normalized://x", polyphonic=True, model_version="v2")
        )
        self.assertEqual(recovered.model_version, "v2")

    def test_quantization_worker_recovery_after_invalid_inputs(self):
        worker = quantization_mod.QuantizationWorker()

        with self.assertRaisesRegex(ValueError, "event_count must be >= 0"):
            worker.process(quantization_mod.QuantizationTaskRequest(event_count=-5, snap_division=16))

        with self.assertRaisesRegex(ValueError, "snap_division must be one of"):
            worker.process(quantization_mod.QuantizationTaskRequest(event_count=5, snap_division=6))

        recovered = worker.process(quantization_mod.QuantizationTaskRequest(event_count=5, snap_division=32))
        self.assertTrue(recovered.had_tuplets)
        self.assertTrue(recovered.deterministic)

    def test_engraving_worker_recovery_after_invalid_request(self):
        worker = engraving_mod.EngravingWorker()

        with self.assertRaisesRegex(ValueError, "musicxml_uri is required"):
            worker.process(engraving_mod.EngravingTaskRequest(musicxml_uri="", dpi=200))

        with self.assertRaisesRegex(ValueError, "dpi must be >= 72"):
            worker.process(engraving_mod.EngravingTaskRequest(musicxml_uri="musicxml://score.xml", dpi=60))

        recovered = worker.process(engraving_mod.EngravingTaskRequest(musicxml_uri="musicxml://score.xml", dpi=200))
        self.assertIn("pdf://musicxml_score.xml.pdf", recovered.pdf_uri)
        self.assertTrue(recovered.readable)


class TestHQAdapterFailureRecovery(unittest.TestCase):
    def setUp(self):
        self.adapter = hq_mod.HQPipelineAdapter()

    def test_hq_adapter_raises_then_recovers_when_degradation_enabled(self):
        with self.assertRaisesRegex(RuntimeError, "degradation is disabled"):
            self.adapter.run(
                hq_mod.HQPipelineRequest(
                    asset_id="hq-fail",
                    source_uri="blob://input.flac",
                    audio_format="flac",
                    simulate_separation_timeout=True,
                    allow_hq_degradation=False,
                )
            )

        recovered = self.adapter.run(
            hq_mod.HQPipelineRequest(
                asset_id="hq-fail",
                source_uri="blob://input.flac",
                audio_format="flac",
                simulate_separation_timeout=True,
                allow_hq_degradation=True,
            )
        )
        self.assertTrue(recovered.degraded_to_draft)
        self.assertIn("musicxml://hq-fail", recovered.draft_result.musicxml_uri)


if __name__ == "__main__":
    unittest.main()
