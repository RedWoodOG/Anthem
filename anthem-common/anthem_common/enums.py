"""
Anthem Common Enumerations.
Standard enums used across the Anthem integration fabric.
"""

from enum import Enum


class GovernanceTier(str, Enum):
    """Constitutional governance authorization tiers."""
    AUTO = "auto"
    T1 = "T1"      # 90-100% autonomous
    T2 = "T2"      # 70-90% with oversight
    T3 = "T3"      # Critical review required
    HALT = "halt"   # Immediate stop


class Region(str, Enum):
    """Geographic regions for jurisdiction-specific governance."""
    US = "US"
    EU = "EU"
    ROW = "ROW"


class EscalationTarget(str, Enum):
    """Valid escalation targets for scenarios exceeding thresholds."""
    URPE = "URPE"
    DOMAIN_CORTEX = "DOMAIN_CORTEX"


class ConstitutionalRiskLevel(str, Enum):
    """Risk severity for bounded autonomy and escalation."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    SEVERE = "severe"


class ReviewAuthority(str, Enum):
    """Authorities that may review or approve governed actions."""
    PLATFORM = "platform"
    HUMAN = "human"
    URPE = "urpe"
    JOINT = "joint"


class AdapterType(str, Enum):
    """Adapter communication protocols."""
    HTTP = "http"
    KAFKA = "kafka"
    GRPC = "grpc"


class IntentTask(str, Enum):
    """High-level task types for routing."""
    QUERY = "query"
    ANALYSIS = "analysis"
    UNDERWRITING = "underwriting"
    SCHEDULING = "scheduling"
    DATA_FETCH = "data_fetch"
    EVALUATION = "evaluation"
    SYNTHESIS = "synthesis"


class Domain(str, Enum):
    """Domain classifications for capability routing."""
    GENERAL = "general"
    FINANCE = "finance"
    CREDIT_RISK = "credit_risk"
    DATA = "data"
    COMPUTE = "compute"
    ENERGY = "energy"
    STRATEGY = "strategy"
    GOVERNANCE = "governance"
    ORCHESTRATION = "orchestration"
