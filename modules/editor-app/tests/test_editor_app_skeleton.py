import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path("modules/editor-app/src/editor_app_skeleton.py")
SPEC = importlib.util.spec_from_file_location("editor_app_skeleton", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FakeClock:
    def __init__(self, *points):
        self._points = list(points)

    def __call__(self):
        if not self._points:
            return 0.0
        return self._points.pop(0)


class TestEditorAppSkeleton(unittest.TestCase):
    def setUp(self):
        self.state = MODULE.EditorState()
        self.note = MODULE.Note(id="n1", start=0.25, duration=0.5, pitch_midi=60)

    def test_add_note_validation_and_duplicate_guard(self):
        self.state.add_note(self.note)

        with self.assertRaises(ValueError):
            self.state.add_note(self.note)
        with self.assertRaises(ValueError):
            self.state.add_note(MODULE.Note(id="bad1", start=-0.1, duration=0.2, pitch_midi=60))
        with self.assertRaises(ValueError):
            self.state.add_note(MODULE.Note(id="bad2", start=0.0, duration=0.0, pitch_midi=60))
        with self.assertRaises(ValueError):
            self.state.add_note(MODULE.Note(id="bad3", start=0.0, duration=0.2, pitch_midi=200))

    def test_delete_move_stretch_guards_and_success(self):
        self.state.add_note(self.note)
        with self.assertRaises(ValueError):
            self.state.delete_note(note_id="missing")

        self.state.move_note(note_id="n1", new_start=0.75)
        self.assertEqual(self.state.notes[0].start, 0.75)

        with self.assertRaises(ValueError):
            self.state.move_note(note_id="n1", new_start=-1)
        with self.assertRaises(ValueError):
            self.state.move_note(note_id="missing", new_start=0.1)

        self.state.stretch_note(note_id="n1", new_duration=1.25)
        self.assertEqual(self.state.notes[0].duration, 1.25)

        with self.assertRaises(ValueError):
            self.state.stretch_note(note_id="n1", new_duration=0)
        with self.assertRaises(ValueError):
            self.state.stretch_note(note_id="missing", new_duration=0.5)

        self.state.delete_note(note_id="n1")
        self.assertEqual(self.state.notes, [])

    def test_quantize_undo_redo_checkpoint(self):
        self.state.add_note(MODULE.Note(id="n1", start=0.24, duration=0.5, pitch_midi=60))
        self.state.add_note(MODULE.Note(id="n2", start=0.49, duration=0.5, pitch_midi=62))

        with self.assertRaises(ValueError):
            self.state.quantize(grid=0)

        self.state.quantize(grid=0.25)
        starts = [n.start for n in self.state.notes]
        self.assertEqual(starts, [0.25, 0.5])

        self.assertTrue(self.state.undo())
        self.assertEqual([n.start for n in self.state.notes], [0.24, 0.49])
        self.assertTrue(self.state.redo())
        self.assertEqual([n.start for n in self.state.notes], [0.25, 0.5])

        checkpoint = self.state.checkpoint()
        self.assertEqual(checkpoint["noteCount"], 2)
        self.assertGreaterEqual(checkpoint["undoDepth"], 1)
        self.assertEqual(checkpoint["metricsCaptured"], 0)

    def test_undo_redo_false_when_empty(self):
        self.assertFalse(self.state.undo())
        self.assertFalse(self.state.redo())

    def test_execute_timed_operation_captures_metric_and_checkpoint_count(self):
        clock = FakeClock(10.0, 10.010)
        state = MODULE.EditorState(clock=clock)

        metric = state.execute_timed_operation(
            operation="add-note",
            action=lambda: state.add_note(MODULE.Note(id="n1", start=0.0, duration=0.5, pitch_midi=60)),
        )

        self.assertEqual(metric.operation, "add-note")
        self.assertAlmostEqual(metric.duration_ms, 10.0, places=5)
        self.assertEqual(state.checkpoint()["metricsCaptured"], 1)

    def test_execute_timed_operation_requires_non_blank_operation(self):
        with self.assertRaisesRegex(ValueError, "operation is required"):
            self.state.execute_timed_operation(operation="   ", action=lambda: None)

    def test_execute_timed_operation_clamps_negative_duration(self):
        state = MODULE.EditorState(clock=FakeClock(5.0, 4.0))

        metric = state.execute_timed_operation(operation="clock-skew", action=lambda: None)

        self.assertEqual(metric.duration_ms, 0.0)

    def test_summarize_latency_and_budget_pass_fail(self):
        state = MODULE.EditorState(clock=FakeClock(0.0, 0.010, 1.0, 1.030))

        state.execute_timed_operation(operation="move-note", action=lambda: None)
        state.execute_timed_operation(operation="move-note", action=lambda: None)

        summary = state.summarize_latency(operation="move-note")
        self.assertEqual(summary["count"], 2.0)
        self.assertAlmostEqual(summary["minMs"], 10.0, places=4)
        self.assertAlmostEqual(summary["maxMs"], 30.0, places=4)
        self.assertAlmostEqual(summary["avgMs"], 20.0, places=4)

        pass_result = state.evaluate_latency_budget(operation="move-note", threshold_ms=35.0)
        self.assertTrue(pass_result.passed)
        self.assertEqual(pass_result.operation, "move-note")
        self.assertEqual(pass_result.threshold_ms, 35.0)
        self.assertAlmostEqual(pass_result.observed_ms, 30.0, places=4)

        fail_result = state.evaluate_latency_budget(operation="move-note", threshold_ms=25.0)
        self.assertFalse(fail_result.passed)

    def test_summarize_latency_and_budget_validation_branches(self):
        with self.assertRaisesRegex(ValueError, "No metrics for operation 'missing'"):
            self.state.summarize_latency(operation="missing")

        self.state.execute_timed_operation(operation="delete-note", action=lambda: None)

        with self.assertRaisesRegex(ValueError, "threshold_ms must be > 0"):
            self.state.evaluate_latency_budget(operation="delete-note", threshold_ms=0)


if __name__ == "__main__":
    unittest.main()
