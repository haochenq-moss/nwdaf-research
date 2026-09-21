import unittest
from unittest.mock import patch

from nwdaf_research.live.kubernetes_observer import ContainerRuntimeObserver, KubernetesObserver


class RuntimeObserverTests(unittest.TestCase):
    @patch("nwdaf_research.live.kubernetes_observer.shutil.which", return_value=None)
    def test_kubernetes_reports_unavailable_without_kubectl(self, _which):
        result = KubernetesObserver().observe()
        self.assertEqual(result.status, "unavailable")

    @patch("nwdaf_research.live.kubernetes_observer.shutil.which", return_value=None)
    def test_container_runtime_reports_unavailable_without_runtime(self, _which):
        result = ContainerRuntimeObserver().observe()
        self.assertEqual(result.status, "unavailable")


if __name__ == "__main__":
    unittest.main()