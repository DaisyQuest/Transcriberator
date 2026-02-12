import importlib.util
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


observability_mod = load_module("orchestrator_observability_test", "modules/orchestrator/observability.py")
draft_mod = load_module("draft_pipeline_observability_test", "modules/orchestrator/draft_pipeline_adapter.py")
hq_mod = load_module("hq_pipeline_observability_test", "modules/orchestrator/hq_pipeline_adapter.py")


class TestObservabilityInstrumentation(unittest.TestCase):
    def test_observability_timed_span_success_and_error_paths(self):
        sink = observability_mod.InMemoryPipelineObservability()
        trace_id = sink.start_trace("test_pipeline", "req-1")

        with sink.timed_span(trace_id, "ok_stage"):
            pass

        with self.assertRaisesRegex(RuntimeError, "boom"):
            with sink.timed_span(trace_id, "bad_stage"):
                raise RuntimeError("boom")

        snapshot = sink.snapshot()
        self.assertEqual(trace_id, "trace-1")
        self.assertEqual(len(snapshot.spans), 2)
        self.assertEqual([s.status for s in snapshot.spans], ["ok", "error"])

        metric_names = [m.name for m in snapshot.metrics]
        self.assertIn("pipeline_runs_total", metric_names)
        self.assertIn("pipeline_stage_success_total", metric_names)
        self.assertIn("pipeline_stage_failures_total", metric_names)

    def test_draft_pipeline_emits_success_observability(self):
        sink = observability_mod.InMemoryPipelineObservability()
        adapter = draft_mod.DraftPipelineAdapter(observability=sink)

        result = adapter.run(
            draft_mod.DraftPipelineRequest(
                asset_id="obs-draft-1",
                source_uri="blob://audio.wav",
                audio_format="wav",
                polyphonic=False,
                snap_division=16,
            )
        )

        self.assertEqual(result.event_count, 12)

        snapshot = sink.snapshot()
        span_names = {span.span_name for span in snapshot.spans}
        self.assertEqual(
            span_names,
            {
                "stage_a_audio",
                "stage_c_tempo",
                "stage_d_transcription",
                "stage_e_quantization",
                "stage_f_notation_export",
            },
        )

        metric_points = {(m.name, m.tags.get("pipeline", ""), m.tags.get("stage", "")) for m in snapshot.metrics}
        self.assertIn(("pipeline_run_success_total", "draft_pipeline", ""), metric_points)
        self.assertIn(("pipeline_runs_total", "draft_pipeline", ""), metric_points)

        success_logs = [l for l in snapshot.logs if l.message == "pipeline.run.success" and l.context.get("pipeline") == "draft_pipeline"]
        self.assertEqual(len(success_logs), 1)

    def test_draft_pipeline_emits_failure_observability(self):
        sink = observability_mod.InMemoryPipelineObservability()
        adapter = draft_mod.DraftPipelineAdapter(observability=sink)

        with self.assertRaisesRegex(ValueError, "Unsupported audio format"):
            adapter.run(
                draft_mod.DraftPipelineRequest(
                    asset_id="obs-draft-2",
                    source_uri="blob://audio.xyz",
                    audio_format="xyz",
                )
            )

        snapshot = sink.snapshot()
        failure_logs = [l for l in snapshot.logs if l.message == "pipeline.run.failure"]
        self.assertEqual(len(failure_logs), 1)
        self.assertEqual(failure_logs[0].context.get("error_type"), "ValueError")

        fail_metrics = [m for m in snapshot.metrics if m.name == "pipeline_run_failures_total"]
        self.assertEqual(len(fail_metrics), 1)
        self.assertEqual(fail_metrics[0].tags.get("pipeline"), "draft_pipeline")

    def test_hq_pipeline_success_observability(self):
        sink = observability_mod.InMemoryPipelineObservability()
        adapter = hq_mod.HQPipelineAdapter(observability=sink)

        result = adapter.run(
            hq_mod.HQPipelineRequest(
                asset_id="obs-hq-1",
                source_uri="blob://audio.wav",
                audio_format="wav",
                simulate_separation_timeout=False,
            )
        )

        self.assertFalse(result.degraded_to_draft)
        snapshot = sink.snapshot()

        span_names = [span.span_name for span in snapshot.spans]
        self.assertIn("stage_b_separation", span_names)

        degraded_metrics = [m for m in snapshot.metrics if m.name == "hq_pipeline_degraded_total"]
        self.assertEqual(degraded_metrics, [])

    def test_hq_pipeline_degraded_observability(self):
        sink = observability_mod.InMemoryPipelineObservability()
        adapter = hq_mod.HQPipelineAdapter(observability=sink)

        result = adapter.run(
            hq_mod.HQPipelineRequest(
                asset_id="obs-hq-2",
                source_uri="blob://audio.mp3",
                audio_format="mp3",
                simulate_separation_timeout=True,
                allow_hq_degradation=True,
            )
        )

        self.assertTrue(result.degraded_to_draft)

        snapshot = sink.snapshot()
        degraded_metrics = [m for m in snapshot.metrics if m.name == "hq_pipeline_degraded_total"]
        self.assertEqual(len(degraded_metrics), 1)

        warning_logs = [l for l in snapshot.logs if l.level == "warning" and l.message == "pipeline.hq.degraded"]
        self.assertEqual(len(warning_logs), 1)

    def test_hq_pipeline_failure_observability_when_degradation_disabled(self):
        sink = observability_mod.InMemoryPipelineObservability()
        adapter = hq_mod.HQPipelineAdapter(observability=sink)

        with self.assertRaisesRegex(RuntimeError, "degradation is disabled"):
            adapter.run(
                hq_mod.HQPipelineRequest(
                    asset_id="obs-hq-3",
                    source_uri="blob://audio.flac",
                    audio_format="flac",
                    simulate_separation_timeout=True,
                    allow_hq_degradation=False,
                )
            )

        snapshot = sink.snapshot()
        failure_logs = [l for l in snapshot.logs if l.message == "pipeline.run.failure" and l.context.get("pipeline") == "hq_pipeline"]
        self.assertEqual(len(failure_logs), 1)

        fail_metrics = [m for m in snapshot.metrics if m.name == "pipeline_run_failures_total" and m.tags.get("pipeline") == "hq_pipeline"]
        self.assertEqual(len(fail_metrics), 1)


if __name__ == "__main__":
    unittest.main()
