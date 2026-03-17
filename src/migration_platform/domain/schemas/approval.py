"""Approval gate schemas."""
from typing import Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic import ConfigDict


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=False)

    status: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=2000)

    @field_validator("comment", mode="before")
    @classmethod
    def coerce_none_to_empty(cls, v: object) -> str:
        """Accept null/undefined/missing from JSON — treat as empty string."""
        if v is None:
            return ""
        return str(v)

    @field_validator("status", mode="before")
    @classmethod
    def normalise_status(cls, v: object) -> str:
        """Normalise status: strip whitespace, accept null → reject, coerce to str."""
        if v is None:
            raise ValueError("status is required: must be 'approved' or 'rejected'")
        return str(v).strip().lower()


class ApprovalResponse(BaseModel):
    migration_id: str
    status: str
    next_phase: str
    message: str
