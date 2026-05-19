"""
URPE API — Risk assessment service.
Thin FastAPI wrapper around the real sensitivity analysis engine.
"""

import logging
from typing import Any, Dict

from fastapi import FastAPI

from anthem_common.schemas import Envelope, NormalizedResult, ErrorDetail
from urpe.core.risk_engine import handle_sensitivity_analysis

logging.basicConfig(level="INFO")
logger = logging.getLogger(__name__)

app = FastAPI(title="Anthem URPE", version="1.0.0")


@app.post("/v1/evaluate")
async def evaluate(envelope: Envelope) -> NormalizedResult:
    """
    Broker-compatible endpoint. Accepts Envelope, returns NormalizedResult.
    Runs real sensitivity analysis on the payload.
    """
    payload = envelope.payload
    if "current_revenue" not in payload:
        return NormalizedResult(
            data=None,
            success=False,
            error=ErrorDetail(
                code="MISSING_FIELD",
                message="current_revenue required for risk evaluation",
                category="client",
            ),
        )

    try:
        result = await handle_sensitivity_analysis(payload)

        return NormalizedResult(
            data=result,
            traces={
                "capability_id": "urpe.evaluate",
                "request_id": envelope.request_id,
            },
            governance=envelope.governance,
        )

    except Exception:
        logger.exception("URPE evaluation failed")
        return NormalizedResult(
            data=None,
            success=False,
            error=ErrorDetail(
                code="URPE_ERROR",
                message="Risk evaluation failed",
                category="server",
                retryable=True,
            ),
        )


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "urpe", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7300)
