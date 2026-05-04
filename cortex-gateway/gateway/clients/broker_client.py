"""
Function Broker Client — calls the broker using mTLS.
"""

import logging
from typing import Any, Dict, Optional

from anthem_common.schemas import Envelope, NormalizedResult, ErrorDetail
from anthem_common.compat import model_dump
from anthem_common.tls import build_tls_client

logger = logging.getLogger(__name__)


class BrokerClient:
    """
    HTTP client for the Function Broker.
    Uses build_tls_client so mTLS is real when certs are configured.
    """

    def __init__(
        self,
        broker_url: str,
        ca_bundle: Optional[str] = None,
        client_cert: Optional[str] = None,
        client_key: Optional[str] = None,
        timeout: float = 60.0,
    ) -> None:
        self.broker_url = broker_url.rstrip("/")
        self.timeout = timeout
        self._client = build_tls_client(
            ca_bundle=ca_bundle,
            client_cert=client_cert,
            client_key=client_key,
            timeout=timeout,
        )

    async def invoke(
        self,
        capability_id: str,
        envelope: Envelope,
    ) -> NormalizedResult:
        """
        Invoke a capability on the broker.
        Returns NormalizedResult on success or error.
        """
        url = f"{self.broker_url}/v1/invoke"
        payload = {
            "capability_id": capability_id,
            "envelope": envelope.to_transport_dict(),
        }

        try:
            response = await self._client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            return NormalizedResult(
                data=data.get("data"),
                details=data.get("details"),
                governance=envelope.governance,
                traces=data.get("traces"),
                success=data.get("success", True),
            )

        except Exception as e:
            logger.exception("Broker invocation failed: %s", capability_id)
            return NormalizedResult(
                data=None,
                success=False,
                error=ErrorDetail(
                    code="BROKER_ERROR",
                    message="Failed to invoke capability via broker",
                    category="server",
                    retryable=True,
                ),
            )

    async def health(self) -> Dict[str, Any]:
        """Check broker health."""
        try:
            response = await self._client.get(f"{self.broker_url}/health")
            return response.json()
        except Exception:
            return {"status": "unreachable", "service": "function-broker"}

    async def close(self) -> None:
        await self._client.aclose()
