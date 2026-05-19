"""
Cortex Gateway Settings — loaded from environment variables.
"""

import os
from pathlib import Path


class GatewaySettings:
    """All gateway config from environment. No hardcoded secrets."""

    def __init__(self) -> None:
        self.environment = os.getenv("ENVIRONMENT", "development")
        self.host = os.getenv("HOST", "0.0.0.0")
        self.port = int(os.getenv("PORT", "8080"))
        self.log_level = os.getenv("LOG_LEVEL", "INFO")

        # Broker
        self.broker_url = os.getenv("BROKER_URL", "http://function-broker:8100")
        self.broker_timeout = int(os.getenv("BROKER_TIMEOUT", "60"))

        # Security
        self.require_api_keys = os.getenv("REQUIRE_API_KEYS", "false").lower() == "true"
        self.cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")

        # mTLS
        self.ca_bundle = os.getenv("CA_BUNDLE") or None
        self.client_cert = os.getenv("CLIENT_CERT") or None
        self.client_key = os.getenv("CLIENT_KEY") or None

        # OPA
        self.opa_url = os.getenv("OPA_URL", "http://opa:8181")
        self.opa_fail_closed = self.environment == "production"

        # Routes
        self.routes_file = Path(os.getenv(
            "ROUTES_FILE",
            str(Path(__file__).parent / "routes.yaml"),
        ))

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


settings = GatewaySettings()
