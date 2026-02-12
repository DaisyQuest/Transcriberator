# Test Suites

## Discovery and Execution Baseline (DT-002)

Use Python's standard `unittest` discovery from the repository root:

- `python -m unittest discover -s tests -t .`

Conventions:
- Test file names must match `test_*.py`.
- Unit tests live in `tests/unit/` and must remain deterministic + fast.
- Integration tests live in `tests/integration/` and may span module boundaries.
- Performance tests live in `tests/performance/` and should focus on repeatable benchmark assertions.

## Coverage Governance

- Maintain at least 95% branch coverage for in-scope changes.
- Add tests for both success paths and failure/guard branches.
- Contract-oriented changes in `modules/shared-contracts/` must include schema governance tests.

## Suite Layout Guidance

- `unit/` for fast deterministic module-level tests.
- `integration/` for cross-module and workflow tests.
- `performance/` for latency and throughput benchmarks.

## Windows Local Reliability

- All test commands must run with default Python tooling on Windows (PowerShell or CMD).
- Avoid shell-specific assumptions in test code.


## Pytest Regression Gate (DT-025)

Primary release gate command:

- `pytest --cov=. --cov-branch --cov-report=term-missing --cov-report=xml --cov-fail-under=95`

Notes:
- `pytest.ini` enforces `--import-mode=importlib` to avoid duplicate test module name collisions.
- `.coveragerc` enforces branch coverage threshold policy (`fail_under = 95`).
- Equivalent Windows command uses `py -m pytest ...` from repository root.
