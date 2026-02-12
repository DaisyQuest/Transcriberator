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


draft_mod = load_module("draft_pipeline_adapter_test", "modules/orchestrator/draft_pipeline_adapter.py")


class TestDraftPipelineIntegration(unittest.TestCase):
    def setUp(self):
        self.adapter = draft_mod.DraftPipelineAdapter()

    def test_draft_pipeline_happy_path_monophonic(self):
        result = self.adapter.run(
            draft_mod.DraftPipelineRequest(
                asset_id="asset-1",
                source_uri="blob://input.wav",
                audio_format="wav",
                polyphonic=False,
                snap_division=16,
            )
        )

        self.assertIn("normalized://asset-1-wav-44100.pcm", result.normalized_uri)
        self.assertIn("tempo-map://", result.tempo_map_uri)
        self.assertEqual(result.event_count, 12)
        self.assertEqual(result.quantized_event_count, 12)
        self.assertFalse(result.had_tuplets)
        self.assertIn("musicxml://asset-1-q12", result.musicxml_uri)
        self.assertIn("midi://asset-1-q12", result.midi_uri)

    def test_draft_pipeline_polyphonic_and_tuplets_branch(self):
        result = self.adapter.run(
            draft_mod.DraftPipelineRequest(
                asset_id="asset-2",
                source_uri="blob://input.flac",
                audio_format="flac",
                polyphonic=True,
                snap_division=32,
            )
        )

        self.assertEqual(result.event_count, 32)
        self.assertTrue(result.had_tuplets)
        self.assertEqual(result.quantized_event_count, 32)

    def test_draft_pipeline_propagates_worker_validation_errors(self):
        with self.assertRaisesRegex(ValueError, "Unsupported audio format"):
            self.adapter.run(
                draft_mod.DraftPipelineRequest(
                    asset_id="asset-3",
                    source_uri="blob://bad",
                    audio_format="aac",
                )
            )

        with self.assertRaisesRegex(ValueError, "snap_division must be one of"):
            self.adapter.run(
                draft_mod.DraftPipelineRequest(
                    asset_id="asset-3",
                    source_uri="blob://bad",
                    audio_format="mp3",
                    snap_division=3,
                )
            )

    def test_stage_f_and_tempo_guard_helpers(self):
        self.assertEqual(
            draft_mod.DraftPipelineAdapter._build_tempo_map_uri("waveform://x.json"),
            "tempo-map://x.tempo.json",
        )

        with self.assertRaisesRegex(ValueError, "waveform_uri must be non-empty"):
            draft_mod.DraftPipelineAdapter._build_tempo_map_uri("  ")

        with self.assertRaisesRegex(ValueError, "asset_id must be non-empty"):
            draft_mod.DraftPipelineAdapter._build_musicxml_uri("", 1)

        with self.assertRaisesRegex(ValueError, "asset_id must be non-empty"):
            draft_mod.DraftPipelineAdapter._build_midi_uri("", 1)


if __name__ == "__main__":
    unittest.main()
