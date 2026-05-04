"""
Anthem Function Broker — Internal capability router.

Loads capabilities from YAML, dispatches to engines via HTTP adapter
with mTLS, enforces governance tier requirements.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from anthem_common.schemas import Envelope, NormalizedResult, ErrorDetail
from anthem_common.tls import build_tls_client

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

CAPABILITIES_FILE = Path(__file__).parent / "config" / "capabilities.yaml"

# ---------------------------------------------------------------------------
# Capability registry
# ---------------------------------------------------------------------------


class Capability:
    """A registered capability backed by an engine endpoint."""

    def __init__(self, data: Dict[str, Any]) -> None:
        self.id: str = data["id"]
        self.display_name: str = data.get("display_name", self.id)
        self.adapter_type: str = data.get("adapter_type", "http")
        self.endpoint: str = data["endpoint"]
        self.default_governance_tier: str = data.get("default_governance_tier", "T2")
        self.domains: List[str] = data.get("domains", [])
        self.timeout: int = data.get("timeout", 30)


class CapabilityRegistry:
    """Loads capabilities from YAML and looks them up by ID."""

    def __init__(self, path: Path) -> None:
        self._capabilities: Dict[str, Capability] = {}
        self._load(path)

    def _load(self, path: Path) -> None:
        if not path.exists():
            logger.warning("Capabilities file not found: %s", path)
            return
        with open(path) as f:
            data = yaml.safe_load(f) or []
        for entry in data:
            cap = Capability(entry)
            self._capabilities[cap.id] = cap
        logger.info("Loaded %d capabilities", len(self._capabilities))

    def get(self, capability_id: str) -> Optional[Capability]:
        return self._capabilities.get(capability_id)

    def list_all(self) -> List[Dict[str, Any]]:
        return [
            {"id": c.id, "display_name": c.display_name, "domains": c.domains}
            for c in self._capabilities.values()
        ]


# ---------------------------------------------------------------------------
# HTTP adapter — dispatches to engines via mTLS
# ---------------------------------------------------------------------------


class HTTPAdapter:
    """Calls engine endpoints using mTLS-configured httpx client."""

    def __init__(self) -> None:
        self._client = build_tls_client(
            ca_bundle=os.getenv("CA_BUNDLE"),
            client_cert=os.getenv("CLIENT_CERT"),
            client_key=os.getenv("CLIENT_KEY"),
            timeout=60.0,
        )

    async def call(
        self,
        capability: Capability,
        envelope: Envelope,
    ) -> NormalizedResult:
        """Dispatch envelope to engine and return NormalizedResult."""
        payload = envelope.to_transport_dict()

        try:
            response = await self._client.post(
                capability.endpoint,
                json=payload,
                timeout=capability.timeout,
            )
            response.raise_for_status()
            data = response.json()

            return NormalizedResult(
                data=data.get("data"),
                details=data.get("details"),
                governance=data.get("governance"),
                traces={
                    "capability_id": capability.id,
                    "engine_endpoint": capability.endpoint,
                    "request_id": envelope.request_id,
                    **(data.get("traces") or {}),
                },
                success=data.get("success", True),
            )

        except Exception:
            logger.exception("Engine call failed: %s → %s", capability.id, capability.endpoint)
            return NormalizedResult(
                data=None,
                success=False,
                error=ErrorDetail(
                    code="ENGINE_ERROR",
                    message=f"Failed to call {capability.display_name}",
                    category="adapter",
                    retryable=True,
                ),
                traces={"capability_id": capability.id},
            )

    async def close(self) -> None:
        await self._client.aclose()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(title="Anthem Function Broker", version="1.0.0")
registry = CapabilityRegistry(CAPABILITIES_FILE)
adapter = HTTPAdapter()


class InvokeRequest(BaseModel):
    capability_id: str
    envelope: Dict[str, Any]


@app.post("/v1/invoke")
async def invoke(req: InvokeRequest) -> Dict[str, Any]:
    """
    Invoke a capability by ID. Called by the Cortex Gateway.
    Dispatches to the engine via HTTP adapter with mTLS.
    """
    capability = registry.get(req.capability_id)
    if not capability:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown capability: {req.capability_id}",
        )

    # Parse envelope from transport dict
    try:
        envelope = Envelope(**req.envelope)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid envelope: {type(e).__name__}",
        )

    logger.info(
        "Invoking %s → %s (tenant=%s)",
        req.capability_id, capability.endpoint, envelope.tenant_id,
    )

    result = await adapter.call(capability, envelope)
    return result.to_transport_dict()


@app.get("/v1/capabilities")
async def list_capabilities():
    """List all registered capabilities."""
    return {"capabilities": registry.list_all()}


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "function-broker",
        "capabilities_loaded": len(registry.list_all()),
    }


@app.on_event("shutdown")
async def shutdown():
    await adapter.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8100")))
