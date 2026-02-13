import importlib.util
import sys
import unittest
from pathlib import Path


def load_module(module_name: str, relative_path: str):
    path = Path(relative_path)
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


MODULE = load_module(
    "worker_transcription_chords_test",
    "modules/worker-transcription/worker_transcription_skeleton.py",
)


class TestTranscriptionWorkerChordIsolation(unittest.TestCase):
    def setUp(self):
        self.worker = MODULE.TranscriptionWorker()

    def test_empty_analysis_frames_keeps_backwards_compatible_defaults(self):
        mono = self.worker.process(MODULE.TranscriptionTaskRequest(source_uri="blob://a", polyphonic=False))
        poly = self.worker.process(MODULE.TranscriptionTaskRequest(source_uri="blob://a", polyphonic=True))

        self.assertEqual(mono.event_count, 12)
        self.assertEqual(poly.event_count, 32)
        self.assertEqual(mono.detected_chords, ())
        self.assertEqual(poly.isolated_pitches, ())
        self.assertEqual(mono.detected_instrument, "unknown")
        self.assertEqual(poly.applied_preset, "auto")
        self.assertEqual(len(mono.execution_plan), 11)
        self.assertEqual(len(poly.chord_strategy), 7)
        self.assertEqual(mono.review_flags, ("confidence_within_threshold",))
        self.assertGreater(mono.confidence, poly.confidence)

    def test_identifies_major_and_minor_chords_and_isolates_stable_pitches(self):
        result = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://song",
                polyphonic=True,
                analysis_frames=(
                    (60, 64, 67),
                    (60, 64, 67),
                    (57, 60, 64),
                    (57, 60, 64),
                    (57, 60, 64, 69),
                    (72,),
                ),
            )
        )

        self.assertEqual(result.event_count, 17)
        self.assertEqual(result.detected_chords, ("C:major", "A:minor"))
        self.assertEqual(result.isolated_pitches, (57, 60, 64, 67))
        self.assertEqual(result.detected_instrument, "acoustic_guitar")
        self.assertEqual(result.applied_preset, "auto")
        self.assertEqual(result.review_flags, ("confidence_within_threshold",))
        self.assertGreaterEqual(result.confidence, 0.7)
        self.assertLessEqual(result.confidence, 0.99)

    def test_normalization_deduplicates_and_sorts_frames_before_scoring(self):
        result = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://dupes",
                polyphonic=True,
                analysis_frames=((67, 60, 60, 64), (64, 67, 60, 60), (72, 72)),
            )
        )

        self.assertEqual(result.event_count, 7)
        self.assertEqual(result.detected_chords, ("C:major",))
        self.assertEqual(result.isolated_pitches, (60, 64, 67))

    def test_identifies_extended_chord_qualities(self):
        augmented = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://aug",
                polyphonic=True,
                analysis_frames=((60, 64, 68),),
            )
        )
        diminished = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://dim",
                polyphonic=True,
                analysis_frames=((62, 65, 68),),
            )
        )
        sus4 = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://sus4",
                polyphonic=True,
                analysis_frames=((67, 72, 74),),
            )
        )

        self.assertEqual(augmented.detected_chords, ("C:augmented",))
        self.assertEqual(diminished.detected_chords, ("D:diminished",))
        self.assertEqual(sus4.detected_chords, ("G:suspended4",))

    def test_unrecognized_chord_shapes_are_ignored(self):
        result = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://cluster",
                polyphonic=True,
                analysis_frames=((60, 61, 62), (60, 61, 62)),
            )
        )
        self.assertEqual(result.detected_chords, ())
        self.assertEqual(result.isolated_pitches, (60, 61, 62))

    def test_validation_errors_for_invalid_request_data(self):
        with self.assertRaisesRegex(ValueError, "source_uri is required"):
            self.worker.process(MODULE.TranscriptionTaskRequest(source_uri="", polyphonic=True))

        with self.assertRaisesRegex(ValueError, "model_version is required"):
            self.worker.process(
                MODULE.TranscriptionTaskRequest(source_uri="blob://audio", polyphonic=True, model_version="")
            )

        with self.assertRaisesRegex(ValueError, "instrument_preset must be one of"):
            self.worker.process(
                MODULE.TranscriptionTaskRequest(
                    source_uri="blob://audio", polyphonic=True, instrument_preset="banjo"
                )
            )

        with self.assertRaisesRegex(ValueError, "cannot contain empty frames"):
            self.worker.process(
                MODULE.TranscriptionTaskRequest(
                    source_uri="blob://audio",
                    polyphonic=True,
                    analysis_frames=((60, 64, 67), ()),
                )
            )

        with self.assertRaisesRegex(ValueError, r"pitches must be in \[0, 127\]"):
            self.worker.process(
                MODULE.TranscriptionTaskRequest(
                    source_uri="blob://audio",
                    polyphonic=True,
                    analysis_frames=((60, 64, 130),),
                )
            )

    def test_pipeline_config_validation_errors(self):
        bad_cases = (
            (MODULE.TranscriptionPipelineConfig(analysis_sample_rate_hz=0), "analysis_sample_rate_hz must be > 0"),
            (MODULE.TranscriptionPipelineConfig(analysis_channels=3), "analysis_channels must be 1"),
            (MODULE.TranscriptionPipelineConfig(frame_ms=10), r"frame_ms must be in \[20, 50\]"),
            (MODULE.TranscriptionPipelineConfig(frame_overlap=1.0), r"frame_overlap must be in \[0.0, 1.0\)"),
            (
                MODULE.TranscriptionPipelineConfig(quantization_subdivisions=()),
                "quantization_subdivisions must be non-empty",
            ),
            (MODULE.TranscriptionPipelineConfig(chord_vocabulary=()), "chord_vocabulary must be non-empty"),
            (
                MODULE.TranscriptionPipelineConfig(low_confidence_threshold=1.1),
                r"low_confidence_threshold must be in \[0.0, 1.0\]",
            ),
        )
        for config, message in bad_cases:
            with self.subTest(config=config):
                with self.assertRaisesRegex(ValueError, message):
                    self.worker.process(
                        MODULE.TranscriptionTaskRequest(
                            source_uri="blob://audio",
                            polyphonic=False,
                            pipeline_config=config,
                        )
                    )

    def test_monophonic_confidence_path_with_analysis_frames(self):
        result = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://melody",
                polyphonic=False,
                analysis_frames=((60,), (60,), (62,), (64,), (64,)),
            )
        )

        self.assertEqual(result.detected_chords, ())
        self.assertEqual(result.event_count, 5)
        self.assertEqual(result.detected_instrument, "flute")
        self.assertGreater(result.confidence, 0.75)

    def test_harmonic_density_bonus_increases_polyphonic_confidence(self):
        sparse = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://sparse",
                polyphonic=True,
                analysis_frames=((60,), (62,), (64,), (65,)),
            )
        )
        dense = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://dense",
                polyphonic=True,
                analysis_frames=((60, 64, 67), (62, 65, 69), (64, 67, 71), (65, 69, 72)),
            )
        )
        self.assertGreater(dense.confidence, sparse.confidence)

    def test_auto_preset_detects_flute_for_high_monophonic_range(self):
        result = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://flute",
                polyphonic=False,
                analysis_frames=((72,), (74,), (76,), (77,), (79,), (81,)),
            )
        )

        self.assertEqual(result.detected_instrument, "flute")
        self.assertEqual(result.applied_preset, "auto")

    def test_auto_preset_detects_acoustic_guitar_for_polyphonic_midrange_chords(self):
        result = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://acoustic",
                polyphonic=True,
                analysis_frames=((43, 47, 50), (45, 48, 52), (43, 47, 50), (47, 50, 55)),
            )
        )

        self.assertEqual(result.detected_instrument, "acoustic_guitar")

    def test_manual_preset_overrides_auto_detection(self):
        result = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://manual",
                polyphonic=False,
                instrument_preset="electric_guitar",
                analysis_frames=((80,), (81,), (83,), (85,)),
            )
        )

        self.assertEqual(result.detected_instrument, "electric_guitar")
        self.assertEqual(result.applied_preset, "electric_guitar")

    def test_execution_plan_reflects_configurability(self):
        result = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://plan",
                polyphonic=False,
                analysis_frames=((72,), (74,), (76,)),
                pipeline_config=MODULE.TranscriptionPipelineConfig(
                    analysis_sample_rate_hz=48_000,
                    analysis_channels=2,
                    frame_ms=40,
                    frame_overlap=0.25,
                    enable_source_separation=False,
                    enable_dynamics_and_articulations=True,
                    quantization_subdivisions=("1/8", "1/16", "triplet"),
                ),
            )
        )

        self.assertIn("sample_rate=48000", result.execution_plan[0])
        self.assertIn("channels=2", result.execution_plan[0])
        self.assertIn("frame_ms=40", result.execution_plan[0])
        self.assertIn("overlap=0.25", result.execution_plan[0])
        self.assertIn("separate_sources(disabled)", result.execution_plan[1])
        self.assertIn("infer_dynamics_articulations(enabled)", result.execution_plan[8])
        self.assertIn("subdivisions=1/8,1/16,triplet", result.execution_plan[5])

    def test_chord_strategy_reflects_custom_vocabulary(self):
        result = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://harmony",
                polyphonic=True,
                analysis_frames=((60, 64, 67),),
                pipeline_config=MODULE.TranscriptionPipelineConfig(
                    chord_vocabulary=("major", "minor", "sus4")
                ),
            )
        )
        self.assertIn("vocabulary=major,minor,sus4", result.chord_strategy[1])

    def test_review_flags_cover_disabled_and_low_confidence_paths(self):
        disabled = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://review-off",
                polyphonic=False,
                analysis_frames=((60,),),
                pipeline_config=MODULE.TranscriptionPipelineConfig(enable_human_review=False),
            )
        )
        self.assertEqual(disabled.review_flags, ("human_review_disabled",))

        low = self.worker.process(
            MODULE.TranscriptionTaskRequest(
                source_uri="blob://review-low",
                polyphonic=True,
                analysis_frames=((60,), (61,), (62,), (63,)),
                pipeline_config=MODULE.TranscriptionPipelineConfig(low_confidence_threshold=0.9),
            )
        )
        self.assertEqual(len(low.review_flags), 2)
        self.assertTrue(low.review_flags[0].startswith("low_confidence_segment("))
        self.assertEqual(
            low.review_flags[1],
            "suggest_actions:re-quantize,key_adjust,merge_split_notes,fix_chords",
        )

    def test_detect_instrument_returns_unknown_when_frames_are_empty(self):
        detected, preset = self.worker._detect_instrument(
            analysis_frames=(),
            preset_name="auto",
            chord_count=0,
            polyphonic=False,
        )
        self.assertEqual((detected, preset), ("unknown", "auto"))

    def test_score_confidence_guard_for_zero_frames(self):
        confidence = self.worker._score_confidence(
            polyphonic=True,
            frame_count=0,
            chord_count=0,
            isolated_pitch_count=0,
            harmonic_density=0,
        )
        self.assertEqual(confidence, 0.0)

    def test_estimate_harmonic_density_empty_and_non_empty_paths(self):
        self.assertEqual(self.worker._estimate_harmonic_density(()), 0.0)
        self.assertEqual(
            self.worker._estimate_harmonic_density(((60,), (60, 64), (60, 64, 67))),
            2.0,
        )

    def test_profile_pitch_span_returns_expected_interval(self):
        self.assertEqual(self.worker._profile_pitch_span("flute"), 36)

    def test_instrument_candidate_scoring_polyphony_branches(self):
        profile = MODULE.TranscriptionWorker._INSTRUMENT_PRESETS["flute"]
        mono_score = self.worker._score_instrument_candidate(
            pitches=[72, 74, 76],
            profile=profile,
            chord_count=0,
            polyphonic=False,
        )
        poly_score = self.worker._score_instrument_candidate(
            pitches=[72, 74, 76],
            profile=profile,
            chord_count=0,
            polyphonic=True,
        )
        self.assertGreater(mono_score, poly_score)


if __name__ == "__main__":
    unittest.main()
