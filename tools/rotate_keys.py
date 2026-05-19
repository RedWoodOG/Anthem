#!/usr/bin/env python3
"""
API Key Rotation Tool.

Rotates API keys with a grace period, ensuring continuous access during transition.

Usage:
    python rotate_keys.py --key-store path/to/api_keys.json --old-key-id KEY_ID [--dry-run]
"""

import argparse
import json
import logging
import secrets
import hashlib
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Get current UTC timestamp."""
    return datetime.now(timezone.utc)


def _hash_key(raw_key: str) -> str:
    """Hash a raw API key using SHA-256."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _generate_key() -> str:
    """Generate a new API key with anthem_ prefix."""
    return f"anthem_{secrets.token_urlsafe(32)}"


def load_key_store(path: Path) -> Dict[str, Any]:
    """
    Load API keys from JSON file.
    
    Expected format:
    {
        "keys": {
            "<key_hash>": {
                "tenant_id": "...",
                "created_at": "...",
                "expires_at": "...",
                "revoked": false,
                "scopes": [...]
            }
        }
    }
    """
    if not path.exists():
        logger.error("Key store not found: %s", path)
        sys.exit(1)
    
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in key store: %s", e)
        sys.exit(1)


def save_key_store(path: Path, data: Dict[str, Any]) -> None:
    """Save API keys to JSON file with pretty formatting."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    logger.info("Key store saved: %s", path)


def find_key_by_id(key_store: Dict[str, Any], key_id: str) -> Optional[tuple]:
    """
    Find a key in the store by its ID (hash).
    Returns (key_hash, key_data) or None.
    """
    keys = key_store.get("keys", {})
    
    # Try direct lookup
    if key_id in keys:
        return (key_id, keys[key_id])
    
    # Try without anthem_ prefix if present
    if key_id.startswith("anthem_"):
        key_hash = _hash_key(key_id)
        if key_hash in keys:
            return (key_hash, keys[key_hash])
    
    return None


def rotate_key(
    key_store: Dict[str, Any],
    old_key_id: str,
    grace_hours: int = 24,
) -> Dict[str, Any]:
    """
    Rotate an API key.
    
    Creates a new key with:
    - New UUID (hash)
    - Same permissions/scopes as old key
    - Same tenant_id
    
    Sets old key to expire in grace_hours.
    
    Returns rotation result with new key details.
    """
    result = find_key_by_id(key_store, old_key_id)
    
    if result is None:
        raise ValueError(f"Key not found: {old_key_id}")
    
    old_key_hash, old_key_data = result
    
    # Check if old key is already revoked
    if old_key_data.get("revoked"):
        raise ValueError(f"Key is already revoked: {old_key_id}")
    
    # Check if old key is already expired
    expires_at = old_key_data.get("expires_at")
    if expires_at:
        expiry = datetime.fromisoformat(expires_at)
        if expiry < _utc_now():
            raise ValueError(f"Key has already expired: {old_key_id}")
    
    # Create new key with same permissions
    new_raw_key = _generate_key()
    new_key_hash = _hash_key(new_raw_key)
    
    now = _utc_now()
    grace_expiry = now + timedelta(hours=grace_hours)
    
    new_key_data = {
        "tenant_id": old_key_data["tenant_id"],
        "created_at": now.isoformat(),
        "expires_at": None,  # New key doesn't expire
        "revoked": False,
        "scopes": old_key_data.get("scopes", ["read", "write"]),
        "rotated_from": old_key_hash,
        "rotation_timestamp": now.isoformat(),
    }
    
    # Set old key to expire after grace period
    old_key_data["expires_at"] = grace_expiry.isoformat()
    old_key_data["rotated_to"] = new_key_hash
    
    # Add new key to store
    keys = key_store.setdefault("keys", {})
    keys[new_key_hash] = new_key_data
    
    return {
        "old_key_id": old_key_hash,
        "old_key_expiry": grace_expiry.isoformat(),
        "new_key_id": new_key_hash,
        "new_raw_key": new_raw_key,
        "tenant_id": new_key_data["tenant_id"],
        "scopes": new_key_data["scopes"],
        "grace_period_hours": grace_hours,
    }


def verify_keys_work(
    key_store: Dict[str, Any],
    old_key_hash: str,
    new_key_hash: str,
) -> Dict[str, bool]:
    """
    Verify both old and new keys are valid during grace period.
    
    Returns dict with validation status for each key.
    """
    keys = key_store.get("keys", {})
    now = _utc_now()
    
    result = {}
    
    # Check old key (should be valid until grace expiry)
    old_key = keys.get(old_key_hash)
    if old_key:
        if old_key.get("revoked"):
            result["old_key_valid"] = False
            result["old_key_reason"] = "revoked"
        else:
            expires_at = old_key.get("expires_at")
            if expires_at:
                expiry = datetime.fromisoformat(expires_at)
                if expiry < now:
                    result["old_key_valid"] = False
                    result["old_key_reason"] = "expired"
                else:
                    result["old_key_valid"] = True
                    result["old_key_reason"] = "valid during grace period"
            else:
                result["old_key_valid"] = True
                result["old_key_reason"] = "no expiry set"
    else:
        result["old_key_valid"] = False
        result["old_key_reason"] = "not found"
    
    # Check new key (should be valid indefinitely)
    new_key = keys.get(new_key_hash)
    if new_key:
        if new_key.get("revoked"):
            result["new_key_valid"] = False
            result["new_key_reason"] = "revoked"
        else:
            expires_at = new_key.get("expires_at")
            if expires_at:
                expiry = datetime.fromisoformat(expires_at)
                if expiry < now:
                    result["new_key_valid"] = False
                    result["new_key_reason"] = "expired"
                else:
                    result["new_key_valid"] = True
                    result["new_key_reason"] = "valid"
            else:
                result["new_key_valid"] = True
                result["new_key_reason"] = "valid (no expiry)"
    else:
        result["new_key_valid"] = False
        result["new_key_reason"] = "not found"
    
    return result


def log_rotation_event(result: Dict[str, Any], log_path: Optional[Path] = None) -> None:
    """Log the rotation event."""
    event = {
        "event": "key_rotation",
        "timestamp": _utc_now().isoformat(),
        "old_key_id": result["old_key_id"],
        "new_key_id": result["new_key_id"],
        "tenant_id": result["tenant_id"],
        "grace_period_hours": result["grace_period_hours"],
        "old_key_expiry": result["old_key_expiry"],
    }
    
    logger.info(
        "KEY_ROTATION: old=%s new=%s tenant=%s grace=%dh expiry=%s",
        result["old_key_id"][:16] + "...",
        result["new_key_id"][:16] + "...",
        result["tenant_id"],
        result["grace_period_hours"],
        result["old_key_expiry"],
    )
    
    if log_path:
        # Append to rotation log
        log_file = log_path / "key_rotation.log"
        with open(log_file, "a") as f:
            f.write(json.dumps(event) + "\n")
        logger.info("Rotation event logged: %s", log_file)


def main():
    parser = argparse.ArgumentParser(
        description="Rotate API keys with grace period",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --key-store api_keys.json --old-key-id abc123
  %(prog)s --key-store api_keys.json --old-key-id abc123 --dry-run
  %(prog)s --key-store api_keys.json --old-key-id abc123 --grace-hours 48
        """,
    )
    
    parser.add_argument(
        "--key-store",
        type=Path,
        required=True,
        help="Path to api_keys.json file",
    )
    
    parser.add_argument(
        "--old-key-id",
        type=str,
        required=True,
        help="Key ID to rotate (hash or raw key)",
    )
    
    parser.add_argument(
        "--grace-hours",
        type=int,
        default=24,
        help="Grace period in hours before old key expires (default: 24)",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate rotation without modifying key store",
    )
    
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=None,
        help="Directory to write rotation logs (optional)",
    )
    
    args = parser.parse_args()
    
    logger.info("Loading key store: %s", args.key_store)
    key_store = load_key_store(args.key_store)
    
    # Find the old key
    result = find_key_by_id(key_store, args.old_key_id)
    if result is None:
        logger.error("Key not found: %s", args.old_key_id)
        sys.exit(1)
    
    old_key_hash, old_key_data = result
    logger.info("Found key: tenant=%s scopes=%s", 
                old_key_data.get("tenant_id"), 
                old_key_data.get("scopes"))
    
    if args.dry_run:
        logger.info("DRY RUN - no changes will be made")
        
        # Simulate rotation
        try:
            simulated_result = rotate_key(
                key_store.copy(),
                args.old_key_id,
                grace_hours=args.grace_hours,
            )
            
            logger.info("Would create new key: %s", 
                       simulated_result["new_key_id"][:16] + "...")
            logger.info("Would set old key expiry: %s", 
                       simulated_result["old_key_expiry"])
            logger.info("New raw key (would be shown once): %s", 
                       simulated_result["new_raw_key"])
            
            # Verify both keys would work
            verification = verify_keys_work(
                key_store,
                old_key_hash,
                simulated_result["new_key_id"],
            )
            logger.info("Verification: old_key=%s new_key=%s",
                       "VALID" if verification.get("old_key_valid") else "INVALID",
                       "VALID" if verification.get("new_key_valid") else "INVALID")
            
            logger.info("DRY RUN complete - use without --dry-run to apply")
            
        except ValueError as e:
            logger.error("Rotation would fail: %s", e)
            sys.exit(1)
        
        return
    
    # Perform actual rotation
    try:
        rotation_result = rotate_key(
            key_store,
            args.old_key_id,
            grace_hours=args.grace_hours,
        )
        
        # Save updated key store
        save_key_store(args.key_store, key_store)
        
        # Log the rotation event
        log_rotation_event(rotation_result, args.log_dir)
        
        # Verify both keys work during grace period
        verification = verify_keys_work(
            key_store,
            rotation_result["old_key_id"],
            rotation_result["new_key_id"],
        )
        
        logger.info("=== ROTATION COMPLETE ===")
        logger.info("Old key ID: %s", rotation_result["old_key_id"])
        logger.info("Old key expires: %s", rotation_result["old_key_expiry"])
        logger.info("New key ID: %s", rotation_result["new_key_id"])
        logger.info("New raw key: %s", rotation_result["new_raw_key"])
        logger.info("Tenant: %s", rotation_result["tenant_id"])
        logger.info("Scopes: %s", rotation_result["scopes"])
        logger.info("Grace period: %d hours", rotation_result["grace_period_hours"])
        logger.info("=== VERIFICATION ===")
        logger.info("Old key status: %s (%s)",
                   "VALID" if verification.get("old_key_valid") else "INVALID",
                   verification.get("old_key_reason", ""))
        logger.info("New key status: %s (%s)",
                   "VALID" if verification.get("new_key_valid") else "INVALID",
                   verification.get("new_key_reason", ""))
        
        # IMPORTANT: New raw key is only shown once
        logger.warning("SECURITY: Save the new raw key now. It will not be shown again.")
        
    except ValueError as e:
        logger.error("Rotation failed: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.exception("Unexpected error during rotation")
        sys.exit(1)


if __name__ == "__main__":
    main()
