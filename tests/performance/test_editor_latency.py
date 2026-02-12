import importlib.util
import statistics
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "modules/editor-app/src/editor_app_skeleton.py"
SPEC = importlib.util.spec_from_file_location("editor_app_skeleton_perf", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class TestEditorLatency(unittest.TestCase):
    def _build_state_with_notes(self, note_count: int) -> object:
        state = MODULE.EditorState()
        for idx in range(note_count):
            state.add_note(
                MODULE.Note(
                    id=f"n{idx}",
                    start=idx * 0.125,
                    duration=0.25,
                    pitch_midi=60 + (idx % 12),
                )
            )
        return state

    def test_move_note_latency_budget_under_50ms(self):
        state = self._build_state_with_notes(64)

        samples = []
        for idx in range(20):
            metric = state.execute_timed_operation(
                operation="move-note",
                action=lambda i=idx: state.move_note(note_id=f"n{i}", new_start=(i * 0.125) + 0.0625),
            )
            samples.append(metric.duration_ms)

        summary = state.summarize_latency(operation="move-note")
        budget = state.evaluate_latency_budget(operation="move-note", threshold_ms=50.0)

        self.assertEqual(summary["count"], 20.0)
        self.assertGreaterEqual(summary["maxMs"], summary["minMs"])
        self.assertLessEqual(summary["avgMs"], 50.0)
        self.assertTrue(budget.passed)
        self.assertLessEqual(statistics.quantiles(samples, n=4)[-1], 50.0)

    def test_quantize_latency_budget_under_50ms(self):
        state = self._build_state_with_notes(128)

        for _ in range(10):
            state.execute_timed_operation(operation="quantize", action=lambda: state.quantize(grid=0.25))

        summary = state.summarize_latency(operation="quantize")
        budget = state.evaluate_latency_budget(operation="quantize", threshold_ms=50.0)

        self.assertEqual(summary["count"], 10.0)
        self.assertTrue(budget.passed)
        self.assertLessEqual(budget.observed_ms, 50.0)


if __name__ == "__main__":
    unittest.main()
