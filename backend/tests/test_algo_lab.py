from algent_backend.labs.algo_lab.datasets import SequenceSpec, generate_sequence
from algent_backend.labs.algo_lab.experiments import (
    SortingExperimentConfig,
    run_experiment,
)


def test_sequence_generation_with_digits():
    spec = SequenceSpec(size=5, min_value=10, max_value=99, digit_width=3, seed=7)
    batch = generate_sequence(spec)
    assert len(batch.values) == 5
    assert len(batch.digits) == 5
    assert all(len(digit_row) == 3 for digit_row in batch.digits)


def test_sorting_experiment_executes_and_reports_metrics():
    cfg = SortingExperimentConfig(
        name="unit-sort",
        algorithm="bubble_sort",
        dataset=SequenceSpec(size=8, seed=11),
        collect_trace=True,
    )
    result = run_experiment(cfg)
    assert result.outcome.sorted_values == sorted(result.dataset.values)
    metric_names = {metric.name for metric in result.metrics}
    assert "latency_ms" in metric_names
    assert "is_sorted" in metric_names
