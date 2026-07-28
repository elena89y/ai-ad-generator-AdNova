import unittest
from pathlib import Path


class DockerDeploymentContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repository_root = Path(__file__).resolve().parents[2]
        cls.compose = (cls.repository_root / "docker-compose.yml").read_text(
            encoding="utf-8"
        )
        cls.generation_unit = (
            cls.repository_root
            / "backend"
            / "deploy"
            / "systemd"
            / "adnova-generation.service"
        ).read_text(encoding="utf-8")

    def test_web_backend_can_reach_host_generation_worker(self) -> None:
        self.assertIn(
            "http://host.docker.internal:8100",
            self.compose,
        )
        self.assertIn(
            "--host 0.0.0.0 --port 8100",
            self.generation_unit,
        )

    def test_runtime_data_and_results_are_persistent_bind_mounts(self) -> None:
        self.assertIn("./runtime/data:/data", self.compose)
        self.assertIn("./runtime/results:/app/results", self.compose)
