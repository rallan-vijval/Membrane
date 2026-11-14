"""The single supported admission suite; historic run shapes remain read-only."""
SUITE_VERSION = "compact-v1"
CASE_COUNT = 3
REPETITIONS = (1, 2)
EXECUTION_COUNT = CASE_COUNT * 2 * len(REPETITIONS)
TESTING_BUDGET_SECONDS = 30
