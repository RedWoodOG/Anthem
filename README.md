# Anthem — Multi-Agent Intelligence Platform

**Version**: 1.0.0
**Status**: In Development

Anthem is a multi-agent orchestration platform where specialized AI agents
collaborate through a shared routing fabric. Each agent runs on a cognitive
harness (Luna) that provides identity persistence, drift prevention,
contradiction detection, and tool-use governance.

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
├── docker-compose.yml      # Deployment (internal ports not exposed)
└── .env.template           # Environment config (never commit .env)
```

## Development

```bash
# Install common package
pip install -e anthem-common/

# Run BUE locally
cd bue && uvicorn api:app --reload --port 9000

# Run tests
pytest anthem-common/tests/
pytest bue/tests/
```

## License

Proprietary — Anthem Technologies
