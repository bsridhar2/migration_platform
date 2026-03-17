"""Domain exception hierarchy."""
from http import HTTPStatus


class MigrationPlatformError(Exception):
    """Base exception for all platform errors."""

    def __init__(self, message: str, http_status: int = 500) -> None:
        super().__init__(message)
        self.message = message
        self.http_status = http_status


class MigrationNotFoundError(MigrationPlatformError):
    def __init__(self, migration_id: str) -> None:
        super().__init__(f"Migration {migration_id!r} not found", HTTPStatus.NOT_FOUND)


class MigrationAlreadyRunningError(MigrationPlatformError):
    def __init__(self, migration_id: str) -> None:
        super().__init__(
            f"Migration {migration_id!r} is already running", HTTPStatus.CONFLICT
        )


class ApprovalGateError(MigrationPlatformError):
    def __init__(self, message: str) -> None:
        super().__init__(message, HTTPStatus.UNPROCESSABLE_ENTITY)


class RepositoryCloneError(MigrationPlatformError):
    def __init__(self, repo_url: str, cause: str) -> None:
        super().__init__(f"Failed to clone {repo_url!r}: {cause}", HTTPStatus.BAD_REQUEST)


class ParseError(MigrationPlatformError):
    def __init__(self, file_path: str, cause: str) -> None:
        super().__init__(f"Parse failed for {file_path!r}: {cause}")


class EmbeddingError(MigrationPlatformError):
    def __init__(self, cause: str) -> None:
        super().__init__(f"Embedding failed: {cause}")


class LLMError(MigrationPlatformError):
    def __init__(self, agent: str, cause: str) -> None:
        super().__init__(f"LLM call failed in {agent!r}: {cause}")


class BuildVerificationError(MigrationPlatformError):
    def __init__(self, project: str, errors: list[str]) -> None:
        joined = "; ".join(errors[:3])
        super().__init__(f"Build failed for {project!r}: {joined}")
