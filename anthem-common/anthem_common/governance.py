"""
Anthem Governance — Real OPA integration.
Actually calls OPA. Fails closed in production.
"""

import logging
from typing import Any, Dict, Optional

import httpx

from .enums import ConstitutionalRiskLevel, GovernanceTier, ReviewAuthority
from .schemas import Envelope, GovernanceMetadata

logger = logging.getLogger(__name__)

DEFAULT_OPA_URL = "http://opa:8181"
OPA_POLICY_PATH = "/v1/data/anthem/governance"


class OPAClient:
    """
    Client that actually queries Open Policy Agent for governance decisions.
    """

    def __init__(
        self,
        opa_url: str = DEFAULT_OPA_URL,
        timeout: float = 5.0,
        fail_closed: bool = True,
    ) -> None:
        self.opa_url = opa_url.rstrip("/")
        self.timeout = timeout
        self.fail_closed = fail_closed

    async def evaluate(
        self,
        envelope: Envelope,
        capability_id: str,
    ) -> GovernanceMetadata:
        """
        Evaluate an envelope against OPA governance policies.

        Returns updated GovernanceMetadata with real scores from OPA.
        """
        opa_input = {
            "input": {
                "tenant_id": envelope.tenant_id,
                "actor": envelope.actor,
                "task": envelope.intent.get("task"),
                "domains": envelope.intent.get("domains", []),
                "capability_id": capability_id,
                "requested_tier": envelope.governance.requested_tier,
                "region": envelope.governance.region,
                "pii_present": bool(envelope.payload),
            }
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.opa_url}{OPA_POLICY_PATH}",
                    json=opa_input,
                )
                response.raise_for_status()
                result = response.json().get("result", {})

            return self._parse_opa_result(result, envelope.governance)

        except httpx.ConnectError:
            logger.error("OPA unreachable at %s", self.opa_url)
            return self._handle_opa_failure(envelope.governance)

        except Exception:
            logger.exception("OPA evaluation failed")
            return self._handle_opa_failure(envelope.governance)

    def _parse_opa_result(
        self,
        result: Dict[str, Any],
        base: GovernanceMetadata,
    ) -> GovernanceMetadata:
        """Parse OPA response into GovernanceMetadata."""
        benefit = result.get("benefit_score", 0.5)
        harm = result.get("harm_score", 0.5)
        tier = self._compute_tier(benefit, harm)
        approval_required = tier in (GovernanceTier.T3, GovernanceTier.HALT)
        risk_level = self._compute_risk_level(harm)

        warnings = list(base.warnings)
        if result.get("warnings"):
            warnings.extend(result["warnings"])

        return GovernanceMetadata(
            requested_tier=base.requested_tier,
            region=base.region,
            pii_masking=base.pii_masking,
            escalation_target=base.escalation_target,
            audit_tags=base.audit_tags,
            benefit_score=round(benefit, 3),
            harm_score=round(harm, 3),
            approval_required=approval_required,
            risk_level=risk_level,
            review_authority=(
                ReviewAuthority.HUMAN if approval_required else ReviewAuthority.PLATFORM
            ),
            warnings=warnings,
        )

    def _handle_opa_failure(self, base: GovernanceMetadata) -> GovernanceMetadata:
        """Handle OPA being unreachable."""
        if self.fail_closed:
            logger.warning("OPA unreachable — DENYING request (fail-closed)")
            return GovernanceMetadata(
                requested_tier=GovernanceTier.HALT,
                region=base.region,
                benefit_score=0.0,
                harm_score=1.0,
                approval_required=True,
                risk_level=ConstitutionalRiskLevel.SEVERE,
                review_authority=ReviewAuthority.HUMAN,
                warnings=["OPA unreachable — request denied (fail-closed policy)"],
            )
        else:
            logger.warning("OPA unreachable — ALLOWING request (dev mode, fail-open)")
            return GovernanceMetadata(
                requested_tier=GovernanceTier.T1,
                region=base.region,
                benefit_score=0.5,
                harm_score=0.1,
                approval_required=False,
                risk_level=ConstitutionalRiskLevel.LOW,
                review_authority=ReviewAuthority.PLATFORM,
                warnings=["OPA unreachable — dev mode fail-open applied"],
            )

    @staticmethod
    def _compute_tier(benefit: float, harm: float) -> GovernanceTier:
        if harm > 0.7:
            return GovernanceTier.HALT
        if harm > 0.4:
            return GovernanceTier.T3
        if harm > 0.2 or benefit < 0.6:
            return GovernanceTier.T2
        return GovernanceTier.T1

    @staticmethod
    def _compute_risk_level(harm: float) -> ConstitutionalRiskLevel:
        if harm > 0.7:
            return ConstitutionalRiskLevel.SEVERE
        if harm > 0.4:
            return ConstitutionalRiskLevel.HIGH
        if harm > 0.2:
            return ConstitutionalRiskLevel.MEDIUM
        return ConstitutionalRiskLevel.LOW
