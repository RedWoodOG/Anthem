"""
Anthem Common Schemas.
Canonical request/response contracts for the integration fabric.
"""

from typing import Any, Dict, List, Optional, Literal
from datetime import datetime, timezone
import hashlib
import json
import uuid

from pydantic import BaseModel, Field

from .compat import PYDANTIC_V2, ConfigDict, field_validator, model_copy, model_dump
from .enums import (
    GovernanceTier,
    Region,
    EscalationTarget,
    ConstitutionalRiskLevel,
    ReviewAuthority,
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Governance metadata
# ---------------------------------------------------------------------------

class GovernanceMetadata(BaseModel):
    """
    Constitutional governance metadata passed through all system calls.
    """
    requested_tier: GovernanceTier = Field(default=GovernanceTier.AUTO)
    region: Region = Field(default=Region.US)
    pii_masking: bool = Field(default=True)
    escalation_target: Optional[EscalationTarget] = None
    audit_tags: Dict[str, str] = Field(default_factory=dict)
    benefit_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    harm_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    approval_required: bool = False
    risk_level: ConstitutionalRiskLevel = Field(default=ConstitutionalRiskLevel.LOW)
    review_authority: ReviewAuthority = Field(default=ReviewAuthority.PLATFORM)
    warnings: List[str] = Field(default_factory=list)

    if PYDANTIC_V2:
        model_config = ConfigDict(use_enum_values=True)
    else:
        class Config:
            use_enum_values = True


# ---------------------------------------------------------------------------
# Request envelope
# ---------------------------------------------------------------------------

class Envelope(BaseModel):
    """
    Universal request envelope for all Anthem operations.
    """
    tenant_id: str = Field(..., description="Tenant identifier")
    actor: str = Field(..., description="Requesting actor identity")
    intent: Dict[str, Any] = Field(..., description="Task + domains")
    payload: Dict[str, Any] = Field(..., description="Operation-specific data")
    policy: Dict[str, Any] = Field(default_factory=dict)
    governance: GovernanceMetadata = Field(default_factory=GovernanceMetadata)
    context: Dict[str, Any] = Field(default_factory=dict)
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=_utc_now)

    if PYDANTIC_V2:
        @field_validator("intent", mode="before")
        @classmethod
        def _validate_intent(cls, v: Dict[str, Any]) -> Dict[str, Any]:
            if "task" not in v:
                raise ValueError("Intent must include 'task' field")
            return v
    else:
        @field_validator("intent", pre=True, allow_reuse=True)
        def _validate_intent(cls, v: Dict[str, Any]) -> Dict[str, Any]:
            if "task" not in v:
                raise ValueError("Intent must include 'task' field")
            return v

    def with_governance(self, governance: GovernanceMetadata) -> "Envelope":
        return model_copy(self, update={"governance": governance})

    def with_context(self, **updates: Any) -> "Envelope":
        new_ctx = {**self.context, **updates}
        return model_copy(self, update={"context": new_ctx})

    def to_transport_dict(self) -> Dict[str, Any]:
        from fastapi.encoders import jsonable_encoder
        return jsonable_encoder(model_dump(self))


# ---------------------------------------------------------------------------
# Response
# ---------------------------------------------------------------------------

class ErrorDetail(BaseModel):
    """
    Sanitized error information. Never exposes internals.
    """
    code: str
    message: str
    category: Literal["client", "server", "governance", "adapter", "timeout"] = "server"
    retryable: bool = False

    @classmethod
    def from_exception(
        cls,
        exc: Exception,
        code: str = "INTERNAL_ERROR",
        category: str = "server",
        retryable: bool = False,
    ) -> "ErrorDetail":
        return cls(
            code=code,
            message="An error occurred during processing",
            category=category,
            retryable=retryable,
        )


class NormalizedResult(BaseModel):
    """
    Universal response format for all Anthem operations.
    """
    data: Any = Field(..., description="Primary result data")
    details: Optional[Dict[str, Any]] = None
    governance: Optional[GovernanceMetadata] = None
    traces: Optional[Dict[str, Any]] = None
    result_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=_utc_now)
    success: bool = True
    error: Optional[ErrorDetail] = None

    def is_success(self) -> bool:
        return self.success and self.error is None

    def with_trace(self, **trace_data: Any) -> "NormalizedResult":
        traces = dict(self.traces or {})
        traces.update(trace_data)
        return model_copy(self, update={"traces": traces})

    def to_transport_dict(self) -> Dict[str, Any]:
        from fastapi.encoders import jsonable_encoder
        return jsonable_encoder(model_dump(self))


# Enable forward references
if hasattr(NormalizedResult, "model_rebuild"):
    NormalizedResult.model_rebuild()
else:
    NormalizedResult.update_forward_refs()


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditRecord(BaseModel):
    """
    Immutable audit record with hash-chain integrity.
    """
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=_utc_now)
    tenant_id: str
    actor: str
    operation: str
    capability_id: Optional[str] = None
    governance: GovernanceMetadata
    result_success: bool
    benefit_score: Optional[float] = None
    harm_score: Optional[float] = None
    previous_hash: Optional[str] = None
    record_hash: Optional[str] = None

    def compute_hash(self) -> str:
        record_data = {
            "record_id": self.record_id,
            "timestamp": self.timestamp.isoformat(),
            "tenant_id": self.tenant_id,
            "actor": self.actor,
            "operation": self.operation,
            "result_success": self.result_success,
            "previous_hash": self.previous_hash,
        }
        record_json = json.dumps(record_data, sort_keys=True)
        return hashlib.sha256(record_json.encode()).hexdigest()
