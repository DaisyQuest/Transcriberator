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
        self.assertGreaterEqual(result.confidence, 0.7)
        self.assertLessEqual(result.confidence, 0.99)

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
