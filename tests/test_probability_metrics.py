import unittest

import numpy as np

from nwdaf_research.experiments.configurations import (
    _bootstrap_f1_ci,
    _probability_metrics,
)


class ProbabilityMetricTests(unittest.TestCase):
    def test_reports_probability_metrics_and_bootstrap_interval(self):
        labels = [0, 0, 1, 1, 1, 1]
        probabilities = np.array([0.1, 0.2, 0.7, 0.8, 0.9, 0.95])
        metrics = _probability_metrics(labels, probabilities)
        interval = _bootstrap_f1_ci(labels, probabilities, repetitions=100)
        self.assertIn("average_precision", metrics)
        self.assertIn("roc_auc", metrics)
        self.assertIn("brier_score", metrics)
        self.assertGreaterEqual(interval["upper_95"], interval["lower_95"])


if __name__ == "__main__":
    unittest.main()