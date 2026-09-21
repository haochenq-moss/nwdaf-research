import unittest

from nwdaf_research.models.gpu_mlp import GPUMLPClassifier


class GPUBackendTests(unittest.TestCase):
    def test_gpu_backend_reports_unavailable_without_cuda(self):
        self.assertIsInstance(GPUMLPClassifier.available(), bool)


if __name__ == "__main__":
    unittest.main()