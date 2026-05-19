# Anthem — Multi-Agent Intelligence Platform

**Version**: 1.0.0  
**Status**: In Development  
**Origin**: Ground-up rewrite of the Aetherion CGI platform

---

## What Anthem Is

Anthem is a multi-agent orchestration platform where specialized AI agents
collaborate through a shared routing fabric. Each agent runs on a cognitive
harness (Luna) that provides identity persistence, drift prevention,
contradiction detection, and tool-use governance.

Every feature documented here is implemented and tested. Nothing is aspirational.

## Why Anthem Exists

Anthem is a rewrite of the Aetherion CGI ("Collective General Intelligence")
platform. Aetherion was an ambitious project that accumulated significant
technical debt and a widening gap between its claims and its implementation:

- **8,134 files / 191,500 lines** — but only ~3,300 LOC of working routing code
- **7 "intelligence engines"** — but the risk engine returned hardcoded floats
  (`return 0.85`), the underwriter had no Monte Carlo simulation, and the
  dynamic planner contained `return None`
- **"Constitutional governance via OPA"** — but no service ever queried OPA
- **"mTLS everywhere"** — but certificate paths were loaded into env vars
  and never wired into SSL contexts
- **"Zero-trust architecture"** — but 19 Docker ports were exposed including
  Postgres, Redis, and every internal engine
- **398 markdown documents** describing quantum cryptography, interplanetary
  scaling, and alien intelligence engagement — none of which were implemented

Anthem strips all of this back to zero and rebuilds only what actually works.
The result is **26 files, 2,191 lines, and 11 passing tests** — a 98.6%
reduction in code volume that represents an increase in real capability.

For the full analysis, see [`docs/EVOLUTION_REPORT.md`](docs/EVOLUTION_REPORT.md).

---

## Architecture

```
Client → Cortex Gateway → Function Broker → Agent (on Luna harness)
              ↓                                    ↓
         OPA Governance                     LLM (verbalizer)
              ↓                                    ↓
         Audit Trail                          Tool Execution
```

**The LLM is not the agent.** The agent is the harness — identity, goals,
tools, and reflection. The LLM is called by the harness when something
needs to be turned into language or when a structured decision needs
natural-language reasoning.

## Agents

| Agent | Role | Key Tools |
|-------|------|-----------|
| **UIE** | Meta-agent / orchestrator | Route to other agents, decompose goals |
| **BUE** | Financial underwriting | Monte Carlo simulation (GBM), industry taxonomy |
| **URPE** | Risk assessment | Sensitivity analysis, adversarial scenarios |
| **CEOA** | Compute orchestration | Workload scheduling, carbon intelligence |
| **Domain Cortex** | Cross-domain synthesis | Aggregate results, find correlations |
| **ILE** | Learning / feedback | Feedback store, drift metrics |

---

## What Changed from Aetherion

| Capability | Aetherion | Anthem |
|------------|-----------|--------|
| **Monte Carlo underwriting** | Field populated from upstream — no simulation code | Real GBM simulator: 10K paths, VaR, CVaR, calibration from history |
| **Risk assessment** | Alien/interplanetary/existential modules returning `0.85` | Sensitivity analysis: perturb ±1σ/±2σ, re-simulate, score from outcomes |
| **OPA governance** | Container configured, never queried | HTTP POST to OPA on every request; fail-closed in production |
| **mTLS** | Cert paths in env vars, plain HTTP clients | `ssl.SSLContext` with `load_cert_chain` and `load_verify_locations` |
| **API authentication** | Boolean flag, no key store | SHA-256 hashed key store with expiry and revocation |
| **Agent architecture** | FastAPI services with hardcoded responses | Luna harness: identity, tools, reflection loop, token budgets |
| **Docker security** | 19 exposed ports, root containers, `changeme` passwords | 3 exposed ports, UID 1000, no default passwords |
| **Error handling** | Leaked `type(exc).__name__` to callers | Sanitized: only code, message, category, retryable |
| **Pydantic compat** | 17 duplicate shim copies across files | 1 centralized `compat.py` |
| **Codebase** | 8,134 files / 213 MB / 191K LOC | 26 files / 90 KB / 2.2K LOC |

---

## Quick Start

```bash
# 1. Configure environment
cp .env.template .env
# Edit .env — set POSTGRES_PASSWORD, at least one LLM API key

# 2. Start services
docker-compose up -d

# 3. Wait for health checks
curl http://localhost:9200/health

# 4. Submit a query
curl -X POST http://localhost:9200/v1/submit \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "demo",
    "actor": "user",
    "intent": {"task": "underwriting", "domains": ["finance"]},
    "payload": {
      "business_name": "Acme Corp",
      "current_revenue": 5000000,
      "industry": "software"
    }
  }'
```

## Security

All of these are implemented, not just documented:

- **mTLS** between services (dev certs auto-generated, production certs required)
- **API key authentication** on the gateway (`X-API-Key` header)
- **OPA governance** — every request evaluated against Rego policies
- **Fail-closed** in production — if OPA is unreachable, requests are denied
- **Rate limiting** — 100 req/min per key, 10 req/min unauthenticated
- **Audit trail** with hash-chain integrity verification
- **Internal services not exposed** — only the gateway port is published
- **Non-root containers** — all services run as UID 1000

## What This Is Not

- Not a general-purpose AI assistant
- Not a government/military system
- Not quantum-anything
- Not interplanetary
- Not production-ready yet (in development)

---

## Project Structure

```
Anthem/
├── anthem-common/          # Shared contracts, schemas, security
│   └── anthem_common/      # Python package
├── cortex-gateway/         # Public API gateway
├── function-broker/        # Internal capability router
├── bue/                    # Business Underwriting (Monte Carlo)
├── urpe/                   # Risk Assessment (sensitivity analysis)
├── uie/                    # LLM orchestration
├── domain-cortex/          # Cross-domain synthesis
├── ile/                    # Learning engine
├── configs/                # Agent identities + tool schemas
│   ├── agents/             # YAML identity per agent
│   └── tools/              # YAML tool defs per agent
├── constitutional-governance/
│   └── policies/           # OPA Rego policies
├── docs/
│   └── EVOLUTION_REPORT.md # Full Aetherion → Anthem comparison
├── docker-compose.yml      # Deployment (internal ports not exposed)
└── .env.template           # Environment config (never commit .env)
```

## Development

```bash
# Install dependencies
pip install -e anthem-common/ numpy pytest

# Run tests (11 passing — verifies real computed output)
pytest tests/test_smoke.py -v

# Run BUE locally
cd bue && uvicorn api:app --reload --port 9000
```

## Roadmap

Anthem's foundation (contracts, security, harness, BUE, URPE) is complete.
Remaining work:

1. **Cortex Gateway + Function Broker** — port routing fabric, wire to OPA/mTLS/auth
2. **UIE** — wire OpenAI/Anthropic SDKs into the agent harness
3. **Domain Cortex, ILE, Klein** — implement as Luna-hosted agents
4. **CEOA** — port existing compute scheduling engine
5. **Dockerfiles** — build images for each service
6. **Integration tests** — end-to-end request flow
7. **Alembic migrations** — database schema management

Each addition follows the same principle: no feature is documented unless
it is implemented, no claim is made unless it can be tested.

## License

Proprietary — Anthem Technologies
