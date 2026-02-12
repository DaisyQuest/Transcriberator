import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


def load_module(module_name: str, relative_path: str):
    path = Path(relative_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


orchestrator_mod = load_module("orchestrator_skeleton", "modules/orchestrator/runtime_skeleton.py")
audio_mod = load_module("audio_worker_skeleton", "modules/worker-audio/worker_audio_skeleton.py")
separation_mod = load_module(
    "separation_worker_skeleton", "modules/worker-separation/worker_separation_skeleton.py"
)
transcription_mod = load_module(
    "transcription_worker_skeleton", "modules/worker-transcription/worker_transcription_skeleton.py"
)
quantization_mod = load_module(
    "quantization_worker_skeleton", "modules/worker-quantization/worker_quantization_skeleton.py"
)
engraving_mod = load_module("engraving_worker_skeleton", "modules/worker-engraving/worker_engraving_skeleton.py")


class TestOrchestratorRuntimeSkeleton(unittest.TestCase):
    def test_draft_mode_skips_separation(self):
        runtime = orchestrator_mod.OrchestratorRuntime(now_provider=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
        result = runtime.run_job(
            orchestrator_mod.OrchestratorJobRequest(job_id="job-1", mode=orchestrator_mod.JobMode.DRAFT)
        )

        self.assertEqual(result.final_status, orchestrator_mod.StageStatus.SUCCEEDED)
        self.assertEqual([record.stage_name for record in result.stage_records], [
            "decode_normalize",
            "source_separation",
            "transcription",
            "quantization",
            "engraving",
        ])
        skipped = [r for r in result.stage_records if r.status is orchestrator_mod.StageStatus.SKIPPED]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0].detail, "skipped for draft mode")

    def test_hq_degrades_when_separation_fails_and_degradation_enabled(self):
        runtime = orchestrator_mod.OrchestratorRuntime(now_provider=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
        result = runtime.run_job(
            orchestrator_mod.OrchestratorJobRequest(
                job_id="job-2", mode=orchestrator_mod.JobMode.HQ, allow_hq_degradation=True
            ),
            fail_stages={"source_separation"},
        )

        self.assertEqual(result.final_status, orchestrator_mod.StageStatus.SUCCEEDED)
        separation_record = result.stage_records[1]
        self.assertEqual(separation_record.stage_name, "source_separation")
        self.assertEqual(separation_record.status, orchestrator_mod.StageStatus.SKIPPED)
        self.assertIn("degraded", separation_record.detail)

    def test_failure_stops_execution_and_final_status_failed(self):
        runtime = orchestrator_mod.OrchestratorRuntime(now_provider=lambda: datetime(2024, 1, 1, tzinfo=timezone.utc))
        result = runtime.run_job(
            orchestrator_mod.OrchestratorJobRequest(job_id="job-3", mode=orchestrator_mod.JobMode.HQ),
            fail_stages={"quantization"},
        )

        self.assertEqual(result.final_status, orchestrator_mod.StageStatus.FAILED)
        self.assertEqual(result.stage_records[-1].stage_name, "quantization")
        self.assertEqual(result.stage_records[-1].status, orchestrator_mod.StageStatus.FAILED)

    def test_final_status_skipped_when_all_records_skipped(self):
        result = orchestrator_mod.OrchestratorJobResult(
            job_id="job-4",
            mode=orchestrator_mod.JobMode.DRAFT,
            run_id="run-job-4",
            stage_records=[
                orchestrator_mod.StageExecutionRecord(
                    stage_name="stage-a",
                    status=orchestrator_mod.StageStatus.SKIPPED,
                    attempts=0,
                    started_at_utc="2024-01-01T00:00:00+00:00",
                    completed_at_utc="2024-01-01T00:00:00+00:00",
                    detail="manual skip",
                )
            ],
        )
        self.assertEqual(result.final_status, orchestrator_mod.StageStatus.SKIPPED)


class TestWorkerSkeletons(unittest.TestCase):
    def test_audio_worker_success_and_validation(self):
        worker = audio_mod.AudioWorker()
        result = worker.process(audio_mod.AudioTaskRequest(asset_id="asset-1", source_uri="blob://a", audio_format="wav"))
        self.assertIn("normalized://asset-1-wav-44100.pcm", result.normalized_uri)

        with self.assertRaisesRegex(ValueError, "Unsupported audio format"):
            worker.process(audio_mod.AudioTaskRequest(asset_id="asset-1", source_uri="blob://a", audio_format="aac"))
        with self.assertRaisesRegex(ValueError, "sample_rate_hz must be > 0"):
            worker.process(
                audio_mod.AudioTaskRequest(
                    asset_id="asset-1", source_uri="blob://a", audio_format="wav", sample_rate_hz=0
                )
            )

    def test_separation_worker_timeout_and_validation(self):
        worker = separation_mod.SeparationWorker()
        timed_out = worker.process(
            separation_mod.SeparationTaskRequest(asset_id="asset-1", normalized_uri="normalized://x", simulate_timeout=True)
        )
        self.assertTrue(timed_out.degraded)
        self.assertEqual(timed_out.stem_uris, {})

        ok = worker.process(
            separation_mod.SeparationTaskRequest(
                asset_id="asset-1", normalized_uri="normalized://x", target_stems=("vocals", "drums")
            )
        )
        self.assertFalse(ok.degraded)
        self.assertEqual(set(ok.stem_uris), {"vocals", "drums"})

        with self.assertRaisesRegex(ValueError, "target_stems cannot be empty"):
            worker.process(
                separation_mod.SeparationTaskRequest(
                    asset_id="asset-1", normalized_uri="normalized://x", target_stems=()
                )
            )

    def test_transcription_worker_polyphonic_and_validation(self):
        worker = transcription_mod.TranscriptionWorker()
        mono = worker.process(
            transcription_mod.TranscriptionTaskRequest(source_uri="blob://audio", polyphonic=False)
        )
        poly = worker.process(
            transcription_mod.TranscriptionTaskRequest(source_uri="blob://audio", polyphonic=True)
        )
        self.assertGreater(poly.event_count, mono.event_count)
        self.assertLess(poly.confidence, mono.confidence)

        with self.assertRaisesRegex(ValueError, "model_version is required"):
            worker.process(
                transcription_mod.TranscriptionTaskRequest(
                    source_uri="blob://audio", polyphonic=True, model_version=""
                )
            )

    def test_quantization_worker_branches(self):
        worker = quantization_mod.QuantizationWorker()
        default = worker.process(quantization_mod.QuantizationTaskRequest(event_count=2, snap_division=16))
        self.assertFalse(default.had_tuplets)
        tuplets = worker.process(quantization_mod.QuantizationTaskRequest(event_count=2, snap_division=32))
        self.assertTrue(tuplets.had_tuplets)

        with self.assertRaisesRegex(ValueError, "event_count must be >= 0"):
            worker.process(quantization_mod.QuantizationTaskRequest(event_count=-1, snap_division=16))
        with self.assertRaisesRegex(ValueError, "snap_division must be one of"):
            worker.process(quantization_mod.QuantizationTaskRequest(event_count=1, snap_division=12))

    def test_engraving_worker_branches(self):
        worker = engraving_mod.EngravingWorker()
        low_dpi = worker.process(engraving_mod.EngravingTaskRequest(musicxml_uri="blob://score.xml", dpi=100))
        self.assertFalse(low_dpi.readable)
        high_dpi = worker.process(engraving_mod.EngravingTaskRequest(musicxml_uri="blob://score.xml", dpi=300))
        self.assertTrue(high_dpi.readable)

        with self.assertRaisesRegex(ValueError, "musicxml_uri is required"):
            worker.process(engraving_mod.EngravingTaskRequest(musicxml_uri="", dpi=150))
        with self.assertRaisesRegex(ValueError, "dpi must be >= 72"):
            worker.process(engraving_mod.EngravingTaskRequest(musicxml_uri="blob://score.xml", dpi=50))


class TestTaskTrackingArtifacts(unittest.TestCase):
    def test_work_checklist_has_phase2_task_group_checked(self):
        text = Path("Work_Checklist.md").read_text(encoding="utf-8")
        self.assertIn("WC-TASK-005", text)
        self.assertIn("DT-010", text)
        self.assertIn("DT-015", text)

    def test_work_description_exists_for_phase2_trackb(self):
        path = Path("workdescriptions/dt-010-dt-015_pipeline-skeletons_work_description.md")
        self.assertTrue(path.is_file())
        content = path.read_text(encoding="utf-8")
        for heading in ["## Summary", "## Work Performed", "## Validation"]:
            with self.subTest(heading=heading):
                self.assertIn(heading, content)


if __name__ == "__main__":
    unittest.main()
