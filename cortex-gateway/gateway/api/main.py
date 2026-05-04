"""
Cortex Gateway API — the front door to Anthem.

Every request passes through:
1. API key authentication (auth.py)
2. OPA governance evaluation (governance.py)
3. Route matching → broker dispatch (broker_client.py via tls.py)
4. Audit logging with hash-chain integrity
"""

import logging
from typing import Any, Dict, List, Optional

import yaml
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from anthem_common.auth import APIKeyManager, require_api_key
from anthem_common.governance import OPAClient
from anthem_common.schemas import (
    AuditRecord,
    Envelope,
    ErrorDetail,
    GovernanceMetadata,
    NormalizedResult,
)

from gateway.clients.broker_client import BrokerClient
from gateway.config.settings import settings

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Anthem Cortex Gateway",
    version="1.0.0",
    description="Multi-agent orchestration gateway with OPA governance and mTLS",
    docs_url="/docs" if not settings.is_production else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Singletons (initialized once, reused across requests)
# ---------------------------------------------------------------------------

_api_key_mgr: Optional[APIKeyManager] = None
_opa_client: Optional[OPAClient] = None
_broker: Optional[BrokerClient] = None
_routes: List[Dict[str, Any]] = []
_audit_chain_hash: Optional[str] = None  # last audit record hash


def _get_api_key_mgr() -> APIKeyManager:
    global _api_key_mgr
    if _api_key_mgr is None:
        _api_key_mgr = APIKeyManager(require_keys=settings.require_api_keys)
        if not settings.require_api_keys:
            _api_key_mgr.bootstrap_admin_key()
    return _api_key_mgr


def _get_opa() -> OPAClient:
    global _opa_client
    if _opa_client is None:
        _opa_client = OPAClient(
            opa_url=settings.opa_url,
            fail_closed=settings.opa_fail_closed,
        )
    return _opa_client


def _get_broker() -> BrokerClient:
    global _broker
    if _broker is None:
        _broker = BrokerClient(
            broker_url=settings.broker_url,
            ca_bundle=settings.ca_bundle,
            client_cert=settings.client_cert,
            client_key=settings.client_key,
            timeout=settings.broker_timeout,
        )
    return _broker


def _load_routes() -> List[Dict[str, Any]]:
    global _routes
    if not _routes and settings.routes_file.exists():
        with open(settings.routes_file) as f:
            _routes = yaml.safe_load(f) or []
        _routes.sort(key=lambda r: r.get("priority", 0), reverse=True)
        logger.info("Loaded %d routes from %s", len(_routes), settings.routes_file)
    return _routes


# ---------------------------------------------------------------------------
# Route matching
# ---------------------------------------------------------------------------

def _match_route(intent: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Match an intent to a route. Returns the first matching route."""
    task = intent.get("task")
    domains = intent.get("domains", [])

    for route in _load_routes():
        match = route.get("match", {})
        if "task" in match and match["task"] != task:
            continue
        if "domains" in match:
            if not any(d in domains for d in match["domains"]):
                continue
        return route

    return None


# ---------------------------------------------------------------------------
# Audit recording
# ---------------------------------------------------------------------------

def _record_audit(envelope: Envelope, result: NormalizedResult, capability: Optional[str]) -> None:
    """Record an audit entry with hash chaining."""
    global _audit_chain_hash

    record = AuditRecord(
        tenant_id=envelope.tenant_id,
        actor=envelope.actor,
        operation=envelope.intent.get("task", "unknown"),
        capability_id=capability,
        governance=envelope.governance,
        result_success=result.success,
        benefit_score=envelope.governance.benefit_score,
        harm_score=envelope.governance.harm_score,
        previous_hash=_audit_chain_hash,
    )
    record.record_hash = record.compute_hash()
    _audit_chain_hash = record.record_hash

    logger.info(
        "AUDIT tenant=%s actor=%s op=%s success=%s hash=%s",
        record.tenant_id,
        record.actor,
        record.operation,
        record.result_success,
        record.record_hash[:12],
    )


# ---------------------------------------------------------------------------
# API key dependency
# ---------------------------------------------------------------------------

_validate_key = None


def get_key_validator():
    global _validate_key
    if _validate_key is None:
        _validate_key = require_api_key(_get_api_key_mgr())
    return _validate_key


async def _auth_dependency(request: Request) -> Dict:
    validator = get_key_validator()
    return await validator(request)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/v1/submit", response_model=NormalizedResult)
async def submit(
    envelope: Envelope,
    request: Request,
    api_key_meta: Dict = Depends(_auth_dependency),
) -> NormalizedResult:
    """
    Submit a request for orchestrated execution.

    Flow:
    1. API key validated (already done by dependency)
    2. OPA governance evaluates the request
    3. Route matched to capability plan
    4. Each plan step dispatched to broker (via mTLS)
    5. Audit recorded with hash chain
    """
    logger.info(
        "Request: tenant=%s actor=%s task=%s",
        envelope.tenant_id, envelope.actor, envelope.intent.get("task"),
    )

    # --- 1. Governance ---
    opa = _get_opa()
    route = _match_route(envelope.intent)
    capability_id = "unknown"
    if route and route.get("plan"):
        capability_id = route["plan"][0].get("capability_id", "unknown")

    governance = await opa.evaluate(envelope, capability_id)
    envelope = envelope.with_governance(governance)

    if governance.requested_tier == "halt":
        result = NormalizedResult(
            data=None,
            success=False,
            error=ErrorDetail(
                code="GOVERNANCE_HALT",
                message="Request denied by governance policy",
                category="governance",
            ),
            governance=governance,
        )
        _record_audit(envelope, result, capability_id)
        return result

    if governance.approval_required:
        logger.warning("Governance requires approval: tier=%s", governance.requested_tier)

    # --- 2. Route matching ---
    if not route:
        result = NormalizedResult(
            data=None,
            success=False,
            error=ErrorDetail(
                code="NO_ROUTE",
                message=f"No route matched for task '{envelope.intent.get('task')}'",
                category="client",
            ),
        )
        _record_audit(envelope, result, None)
        return result

    # --- 3. Execute plan steps via broker ---
    broker = _get_broker()
    step_results: Dict[str, NormalizedResult] = {}

    for step in route["plan"]:
        step_id = step["id"]
        step_capability = step["capability_id"]

        # Check dependencies
        deps = step.get("dependencies", [])
        dep_failed = any(
            step_results.get(d) and not step_results[d].success
            for d in deps
        )
        if dep_failed:
            logger.warning("Skipping step %s — dependency failed", step_id)
            continue

        # Inject dependency data into payload via input_mapping
        step_envelope = envelope
        if step.get("input_mapping"):
            import copy
            merged_payload = copy.deepcopy(envelope.payload)
            for target_key, source_path in step["input_mapping"].items():
                parts = source_path.split(".")
                if len(parts) >= 2:
                    source_step = parts[0]
                    source_result = step_results.get(source_step)
                    if source_result and source_result.success and source_result.data:
                        val = source_result.data
                        for part in parts[1:]:
                            if isinstance(val, dict):
                                val = val.get(part)
                            else:
                                val = None
                                break
                        if val is not None:
                            merged_payload[target_key] = val
            step_envelope = envelope.with_context(
                step_id=step_id,
                capability_id=step_capability,
            )
            from anthem_common.compat import model_copy
            step_envelope = model_copy(step_envelope, update={"payload": merged_payload})

        logger.info("Dispatching step %s → %s", step_id, step_capability)
        result = await broker.invoke(step_capability, step_envelope)
        step_results[step_id] = result

        if not result.success:
            logger.warning("Step %s failed: %s", step_id, result.error)
            break

    # --- 4. Synthesize final result ---
    if not step_results:
        final = NormalizedResult(
            data=None,
            success=False,
            error=ErrorDetail(code="NO_STEPS", message="No plan steps executed", category="server"),
        )
    elif len(step_results) == 1:
        final = list(step_results.values())[0]
    else:
        # Multi-step: combine results
        combined_data = {
            step_id: r.data for step_id, r in step_results.items() if r.success
        }
        any_failed = any(not r.success for r in step_results.values())
        final = NormalizedResult(
            data=combined_data,
            success=not any_failed,
            governance=governance,
            traces={"plan_steps": list(step_results.keys())},
        )

    # --- 5. Audit ---
    _record_audit(envelope, final, capability_id)

    return final


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "cortex-gateway", "version": "1.0.0"}


@app.get("/ready")
async def ready():
    broker_health = await _get_broker().health()
    routes_loaded = len(_load_routes())
    broker_ok = broker_health.get("status") == "healthy"

    return {
        "ready": broker_ok and routes_loaded > 0,
        "routes_loaded": routes_loaded,
        "broker": broker_health,
    }


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def startup():
    logger.info("Starting Cortex Gateway")
    logger.info("Environment: %s", settings.environment)
    logger.info("Broker: %s", settings.broker_url)
    logger.info("OPA: %s (fail_closed=%s)", settings.opa_url, settings.opa_fail_closed)
    logger.info("API keys required: %s", settings.require_api_keys)
    logger.info("mTLS configured: %s", bool(settings.ca_bundle))
    _load_routes()


@app.on_event("shutdown")
async def shutdown():
    if _broker:
        await _broker.close()


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "error": {"code": f"HTTP_{exc.status_code}", "message": exc.detail}},
    )


@app.exception_handler(Exception)
async def general_error(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"success": False, "error": {"code": "INTERNAL_ERROR", "message": "An error occurred"}},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
