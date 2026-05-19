"""Verify all modules import cleanly."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.path.insert(0, str(root / "cortex-gateway"))
sys.path.insert(0, str(root / "function-broker"))

# anthem_common
from anthem_common.schemas import Envelope, NormalizedResult, AuditRecord, ErrorDetail, GovernanceMetadata
from anthem_common.enums import GovernanceTier, Region, ConstitutionalRiskLevel
from anthem_common.compat import model_copy, model_dump, PYDANTIC_V2
from anthem_common.tls import build_tls_client, build_ssl_context
from anthem_common.auth import APIKeyManager, require_api_key
from anthem_common.governance import OPAClient
from anthem_common.harness import AgentHarness, ToolRegistry, ToolDefinition, ReflectionLoop, load_agent_identity

# BUE
from bue.simulation.monte_carlo import MonteCarloSimulator, SimulationInputs, handle_monte_carlo_simulate
from bue.simulation.taxonomy import get_industry_defaults

# URPE
from urpe.core.risk_engine import RiskEngine, RiskFactor, SensitivityAnalysis, handle_sensitivity_analysis

# Gateway
from gateway.config.settings import GatewaySettings
from gateway.clients.broker_client import BrokerClient

# Broker
from broker.main import CapabilityRegistry, HTTPAdapter, Capability

print("All imports successful")
print(f"Pydantic v2: {PYDANTIC_V2}")
identity = load_agent_identity("bue")
print(f"BUE identity: {identity.name}")
print(f"BUE axioms: {len(identity.axioms)}")
print(f"BUE constraints: {len(identity.constraints)}")
defaults = get_industry_defaults("software")
print(f"Software defaults: growth={defaults['growth_rate']}, vol={defaults['volatility']}")
