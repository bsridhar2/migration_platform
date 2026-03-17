"""Workflows package."""
from migration_platform.workflows.state import MigrationState
from migration_platform.workflows.migration_graph import build_migration_graph
__all__ = ["MigrationState", "build_migration_graph"]
