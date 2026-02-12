import importlib.util
import unittest
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


hq_mod = load_module("hq_pipeline_adapter_test", "modules/orchestrator/hq_pipeline_adapter.py")


class TestHQPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.adapter = hq_mod.HQPipelineAdapter()

    def test_hq_success_with_stems(self):
        result = self.adapter.run(
            hq_mod.HQPipelineRequest(
                asset_id="hq-1",
                source_uri="blob://input.wav",
                audio_format="wav",
            )
        )

        self.assertFalse(result.degraded_to_draft)
        self.assertGreater(result.separation_quality_score, 0)
        self.assertEqual(set(result.stem_uris), {"vocals", "other"})
        self.assertEqual(result.draft_result.event_count, 32)

    def test_hq_degradation_allowed(self):
        result = self.adapter.run(
            hq_mod.HQPipelineRequest(
                asset_id="hq-2",
                source_uri="blob://input.mp3",
                audio_format="mp3",
                simulate_separation_timeout=True,
                allow_hq_degradation=True,
            )
        )

        self.assertTrue(result.degraded_to_draft)
        self.assertEqual(result.stem_uris, {})
        self.assertEqual(result.separation_quality_score, 0.0)
        self.assertIn("musicxml://", result.draft_result.musicxml_uri)

    def test_hq_degradation_disallowed_raises(self):
        with self.assertRaisesRegex(RuntimeError, "degradation is disabled"):
            self.adapter.run(
                hq_mod.HQPipelineRequest(
                    asset_id="hq-3",
                    source_uri="blob://input.flac",
                    audio_format="flac",
                    simulate_separation_timeout=True,
                    allow_hq_degradation=False,
                )
            )


if __name__ == "__main__":
    unittest.main()
