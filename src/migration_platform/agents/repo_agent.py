"""Repo Agent — clones repository and builds file manifest."""
from __future__ import annotations
import os
from pathlib import Path
from typing import Any
import git
from migration_platform.config.settings import get_settings
from migration_platform.domain.models.migration import FileType, MigrationStatus
from migration_platform.agents.base import BaseAgent
from migration_platform.workflows.state import MigrationState

_EXT_TO_TYPE: dict[str, FileType] = {
    ".java": FileType.JAVA,
    ".jsp":  FileType.JSP,
    ".jspx": FileType.JSP,
    ".js":   FileType.JS,
    ".html": FileType.HTML,
    ".htm":  FileType.HTML,
    ".css":  FileType.CSS,
    ".xml":  FileType.XML,
    ".wsdl": FileType.WSDL,
    ".sql":  FileType.SQL,
    ".properties": FileType.PROPERTIES,
}

_ENTRY_POINT_NAMES = {
    "web.xml", "index.jsp", "index.html", "home.jsp",
}

_IGNORE_DIRS = {
    ".git", ".svn", "target", "build", "node_modules",
    ".idea", ".vscode", "__pycache__", "test-output",
}


class RepoAgent(BaseAgent):
    """
    Clones the Git repository and produces:
    - file_manifest: typed list of all source files
    - entry_points: detected application entry points
    """

    def run(self, state: MigrationState) -> MigrationState:
        self._logger.info("RepoAgent starting", migration_id=state["migration_id"])
        settings = get_settings()

        repo_dir = Path(settings.repos_dir) / state["migration_id"]

        try:
            if repo_dir.exists():
                self._logger.info("Repo already cloned, reusing", path=str(repo_dir))
                repo = git.Repo(repo_dir)
            else:
                self._logger.info("Cloning repository", url=state["repo_url"])
                repo = git.Repo.clone_from(
                    state["repo_url"], repo_dir, depth=1
                )
        except git.GitCommandError as exc:
            state["errors"].append(f"RepoAgent clone failed: {exc}")
            state["current_phase"] = MigrationStatus.FAILED.value
            return state

        manifest: list[dict[str, str]] = []
        entry_points: list[str] = []
        counts: dict[str, int] = {}

        for root, dirs, file_names in os.walk(repo_dir):
            # Prune ignored directories in-place
            dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
            for name in file_names:
                full_path = Path(root) / name
                rel = str(full_path.relative_to(repo_dir))
                ext = full_path.suffix.lower()
                ftype = _EXT_TO_TYPE.get(ext, FileType.OTHER)
                if ftype == FileType.OTHER:
                    continue

                manifest.append({"file_path": rel, "file_type": ftype.value})
                counts[ftype.value] = counts.get(ftype.value, 0) + 1

                if name in _ENTRY_POINT_NAMES:
                    entry_points.append(rel)

        state["repo_local_path"] = str(repo_dir)
        state["file_manifest"] = {"files": manifest, "counts": counts, "root": str(repo_dir)}
        state["entry_points"] = entry_points
        state["current_phase"] = "ingested"

        self._logger.info(
            "RepoAgent complete",
            total_files=len(manifest),
            entry_points=len(entry_points),
            counts=counts,
        )
        return state
