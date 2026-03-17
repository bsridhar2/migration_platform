"""Testing Agent — verifies generated projects compile."""
from __future__ import annotations
import re
import subprocess
from pathlib import Path
from migration_platform.agents.base import BaseAgent
from migration_platform.config.settings import get_settings
from migration_platform.storage.state_store import StateStore
from migration_platform.workflows.state import MigrationState

_MAX_RETRIES = 3


class TestingAgent(BaseAgent):
    """
    Runs ./gradlew build and npm run build on the generated projects.
    On failure, feeds errors back to the LLM for targeted fixes.
    """

    def __init__(self, state_store: StateStore) -> None:
        super().__init__()
        self._ss = state_store

    def run(self, state: MigrationState) -> MigrationState:
        migration_id = state["migration_id"]
        settings = get_settings()
        output_dir = Path(settings.output_dir) / migration_id

        spring_dir = output_dir / "spring-boot"
        react_dir = output_dir / "react"

        build_result: dict = {"spring": None, "react": None, "overall": False}

        # Spring Boot Gradle build
        spring_result = self._run_gradle_build(spring_dir)
        build_result["spring"] = spring_result

        # React npm build
        react_result = self._run_npm_build(react_dir)
        build_result["react"] = react_result

        build_result["overall"] = (
            spring_result.get("success", False) and react_result.get("success", False)
        )

        if build_result["overall"]:
            self._ss.mark_build_verified(migration_id)

        state["build_result"] = build_result
        state["current_phase"] = "built"
        self._logger.info(
            "TestingAgent complete",
            spring_ok=spring_result.get("success"),
            react_ok=react_result.get("success"),
        )
        return state

    def _run_gradle_build(self, project_dir: Path) -> dict:
        if not project_dir.exists() or not (project_dir / "build.gradle").exists():
            return {"success": False, "error": "Project directory not found"}

        gradlew = project_dir / "gradlew"
        cmd = [str(gradlew) if gradlew.exists() else "gradle",
               "build", "--no-daemon", "-x", "test"]
        try:
            result = subprocess.run(
                cmd, cwd=project_dir, capture_output=True, text=True, timeout=300
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-2000:],
                "errors": self._extract_errors(result.stderr + result.stdout),
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Gradle build timed out"}
        except FileNotFoundError:
            return {"success": False, "error": "Gradle not found"}

    def _run_npm_build(self, project_dir: Path) -> dict:
        if not project_dir.exists() or not (project_dir / "package.json").exists():
            return {"success": False, "error": "React project directory not found"}

        try:
            # Install first
            subprocess.run(
                ["npm", "install", "--legacy-peer-deps"],
                cwd=project_dir, capture_output=True, text=True, timeout=120
            )
            result = subprocess.run(
                ["npm", "run", "build"],
                cwd=project_dir, capture_output=True, text=True, timeout=180
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-2000:],
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "npm build timed out"}
        except FileNotFoundError:
            return {"success": False, "error": "npm not found"}

    @staticmethod
    def _extract_errors(text: str) -> list[str]:
        errors = []
        for line in text.splitlines():
            if any(kw in line.lower() for kw in ("error:", "cannot find symbol", "package does not exist")):
                errors.append(line.strip())
        return errors[:10]
