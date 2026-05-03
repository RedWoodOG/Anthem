"""
Anthem mTLS — Real mutual TLS client factory.
Every inter-service HTTP client uses this instead of plain httpx.
"""

import logging
import ssl
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


def build_ssl_context(
    ca_bundle: Optional[str] = None,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
) -> Optional[ssl.SSLContext]:
    """
    Build an SSL context for mutual TLS.

    Returns None if no certs are configured (local dev without TLS).
    Raises if certs are configured but files are missing.
    """
    if not ca_bundle and not client_cert:
        logger.warning("No TLS certificates configured — running without mTLS")
        return None

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2

    if ca_bundle:
        ca_path = Path(ca_bundle)
        if not ca_path.exists():
            raise FileNotFoundError(f"CA bundle not found: {ca_bundle}")
        ctx.load_verify_locations(str(ca_path))
        logger.info("Loaded CA bundle: %s", ca_bundle)

    if client_cert and client_key:
        cert_path = Path(client_cert)
        key_path = Path(client_key)
        if not cert_path.exists():
            raise FileNotFoundError(f"Client cert not found: {client_cert}")
        if not key_path.exists():
            raise FileNotFoundError(f"Client key not found: {client_key}")
        ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
        logger.info("Loaded client cert: %s", client_cert)

    return ctx


def build_tls_client(
    ca_bundle: Optional[str] = None,
    client_cert: Optional[str] = None,
    client_key: Optional[str] = None,
    timeout: float = 30.0,
) -> httpx.AsyncClient:
    """
    Build an httpx.AsyncClient with mTLS configured.

    If no certs are provided, returns a plain client (local dev).
    """
    ssl_ctx = build_ssl_context(ca_bundle, client_cert, client_key)

    if ssl_ctx:
        return httpx.AsyncClient(verify=ssl_ctx, timeout=timeout)

    return httpx.AsyncClient(timeout=timeout)
