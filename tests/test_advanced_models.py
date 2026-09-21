import unittest

import numpy as np

from nwdaf_research.models.advanced import evaluate_advanced


class AdvancedModelTests(unittest.TestCase):
    def test_normalized_tuned_multiseed_calibrated_evaluation(self):
        train_x = np.asarray([[0.0], [0.1], [0.9], [1.0], [0.2], [0.8]])
        train_y = [0, 0, 1, 1, 0, 1]
        result = evaluate_advanced(train_x, train_y, train_x, train_y, train_x, train_y, seeds=(7, 42))
        self.assertEqual(len(result.seed_results), 2)
        self.assertIn("brier_score", result.calibrated)


if __name__ == "__main__":
    unittest.main()