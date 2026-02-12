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
        self.assertGreater(result.confidence, 0.75)


if __name__ == "__main__":
    unittest.main()
