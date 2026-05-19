"""
Audit record hash-chain integrity tests.
Verifies audit trail immutability and tamper detection.
"""

import pytest
from datetime import datetime, timezone
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from anthem_common.schemas import AuditRecord, GovernanceMetadata
from anthem_common.enums import GovernanceTier, Region, ConstitutionalRiskLevel, ReviewAuthority


class TestAuditChainIntegrity:
    """Test audit chain creation and verification."""

    def test_audit_chain_is_verifiable(self):
        """Creates 3 AuditRecord objects with chained hashes, verifies chain integrity."""
        base_governance = GovernanceMetadata(
            requested_tier=GovernanceTier.T1,
            region=Region.US,
            benefit_score=0.9,
            harm_score=0.1,
        )

        # Create first record (genesis - no prior hash)
        record1 = AuditRecord(
            tenant_id="tenant-001",
            actor="user-alpha",
            operation="query",
            capability_id="uie.query",
            governance=base_governance,
            result_success=True,
            benefit_score=0.9,
            harm_score=0.1,
            previous_hash=None,
        )
        record1.record_hash = record1.compute_hash()

        # Create second record (chains to record1)
        record2 = AuditRecord(
            tenant_id="tenant-001",
            actor="user-alpha",
            operation="underwriting",
            capability_id="bue.underwrite",
            governance=base_governance,
            result_success=True,
            benefit_score=0.8,
            harm_score=0.2,
            previous_hash=record1.record_hash,
        )
        record2.record_hash = record2.compute_hash()

        # Create third record (chains to record2)
        record3 = AuditRecord(
            tenant_id="tenant-001",
            actor="user-beta",
            operation="analysis",
            capability_id="ceoa.analyze",
            governance=base_governance,
            result_success=True,
            benefit_score=0.7,
            harm_score=0.3,
            previous_hash=record2.record_hash,
        )
        record3.record_hash = record3.compute_hash()

        # Verify chain integrity
        assert record1.previous_hash is None, "Genesis record must have no prior hash"
        assert record1.record_hash is not None, "Record 1 must have computed hash"
        
        assert record2.previous_hash == record1.record_hash, "Record 2 must chain to Record 1"
        assert record2.record_hash is not None, "Record 2 must have computed hash"
        
        assert record3.previous_hash == record2.record_hash, "Record 3 must chain to Record 2"
        assert record3.record_hash is not None, "Record 3 must have computed hash"

        # Verify chain by walking backwards
        chain = [record3, record2, record1]
        for i, record in enumerate(chain[:-1]):
            assert record.previous_hash == chain[i + 1].record_hash, \
                f"Chain broken at record {i}: previous_hash mismatch"

    def test_audit_chain_detects_tampering(self):
        """Modifies one record, verifies chain breaks."""
        base_governance = GovernanceMetadata(
            requested_tier=GovernanceTier.T2,
            region=Region.US,
        )

        # Build a 3-record chain
        record1 = AuditRecord(
            tenant_id="tenant-001",
            actor="user-alpha",
            operation="query",
            governance=base_governance,
            result_success=True,
            previous_hash=None,
        )
        record1.record_hash = record1.compute_hash()

        record2 = AuditRecord(
            tenant_id="tenant-001",
            actor="user-alpha",
            operation="underwriting",
            governance=base_governance,
            result_success=True,
            previous_hash=record1.record_hash,
        )
        record2.record_hash = record2.compute_hash()

        record3 = AuditRecord(
            tenant_id="tenant-001",
            actor="user-alpha",
            operation="analysis",
            governance=base_governance,
            result_success=True,
            previous_hash=record2.record_hash,
        )
        record3.record_hash = record3.compute_hash()

        # Verify original chain is valid
        assert record2.previous_hash == record1.record_hash
        assert record3.previous_hash == record2.record_hash

        # Tamper with record1's operation field
        tampered_record1 = AuditRecord(
            record_id=record1.record_id,
            timestamp=record1.timestamp,
            tenant_id="tenant-001",
            actor="user-alpha",
            operation="TAMPERED_OPERATION",  # Changed!
            governance=base_governance,
            result_success=True,
            previous_hash=None,
        )
        tampered_record1.record_hash = tampered_record1.compute_hash()

        # The tampered hash won't match what record2 expects
        assert record2.previous_hash != tampered_record1.record_hash, \
            "Chain should break after tampering"

        # Verify we can detect the tampering
        def verify_chain(records):
            """Returns True if chain is valid, False if tampering detected."""
            for i, record in enumerate(records[:-1]):
                if record.previous_hash != records[i + 1].record_hash:
                    return False
            # Also verify each record's self-hash
            for record in records:
                expected_hash = record.compute_hash()
                if record.record_hash != expected_hash:
                    return False
            return True

        # Original chain is valid
        assert verify_chain([record3, record2, record1]) is True

        # Tampered chain is invalid
        assert verify_chain([record3, record2, tampered_record1]) is False

    def test_audit_record_has_required_fields(self):
        """Verifies AuditRecord has request_id, timestamp, capability, tier, prior_hash, content_hash."""
        base_governance = GovernanceMetadata(
            requested_tier=GovernanceTier.T1,
            region=Region.US,
        )

        record = AuditRecord(
            tenant_id="tenant-001",
            actor="user-alpha",
            operation="query",
            capability_id="uie.query",
            governance=base_governance,
            result_success=True,
            previous_hash="abc123",
        )
        record.record_hash = record.compute_hash()

        # Verify all required fields exist and are populated
        assert hasattr(record, 'record_id'), "AuditRecord must have record_id"
        assert record.record_id is not None, "record_id must be populated"
        
        assert hasattr(record, 'timestamp'), "AuditRecord must have timestamp"
        assert record.timestamp is not None, "timestamp must be populated"
        assert isinstance(record.timestamp, datetime), "timestamp must be datetime"
        
        assert hasattr(record, 'capability_id'), "AuditRecord must have capability_id"
        # capability_id can be None for some operations, but field must exist
        
        # Tier comes from governance metadata
        assert hasattr(record, 'governance'), "AuditRecord must have governance"
        assert hasattr(record.governance, 'requested_tier'), "Governance must have requested_tier"
        
        assert hasattr(record, 'previous_hash'), "AuditRecord must have previous_hash"
        # previous_hash can be None for genesis records
        
        assert hasattr(record, 'record_hash'), "AuditRecord must have record_hash (content hash)"
        assert record.record_hash is not None, "record_hash must be computed"
        assert len(record.record_hash) == 64, "record_hash must be SHA-256 (64 hex chars)"

    def test_audit_hash_is_deterministic(self):
        """Same inputs produce same hash."""
        base_governance = GovernanceMetadata(
            requested_tier=GovernanceTier.T1,
            region=Region.US,
        )

        # Create two records with identical data
        # Note: record_id and timestamp are auto-generated, so we must set them explicitly
        fixed_time = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        fixed_id = "fixed-record-id-12345"

        record1 = AuditRecord(
            record_id=fixed_id,
            timestamp=fixed_time,
            tenant_id="tenant-001",
            actor="user-alpha",
            operation="query",
            capability_id="uie.query",
            governance=base_governance,
            result_success=True,
            benefit_score=0.9,
            harm_score=0.1,
            previous_hash=None,
        )
        record1.record_hash = record1.compute_hash()

        record2 = AuditRecord(
            record_id=fixed_id,
            timestamp=fixed_time,
            tenant_id="tenant-001",
            actor="user-alpha",
            operation="query",
            capability_id="uie.query",
            governance=base_governance,
            result_success=True,
            benefit_score=0.9,
            harm_score=0.1,
            previous_hash=None,
        )
        record2.record_hash = record2.compute_hash()

        # Hashes must be identical
        assert record1.record_hash == record2.record_hash, \
            "Identical records must produce identical hashes"

        # Verify the hash is deterministic by computing it again
        recomputed_hash = record1.compute_hash()
        assert record1.record_hash == recomputed_hash, \
            "Hash must be deterministic across multiple computations"

        # Verify that changing even one field changes the hash
        record3 = AuditRecord(
            record_id=fixed_id,
            timestamp=fixed_time,
            tenant_id="tenant-001",
            actor="user-alpha",
            operation="query",
            capability_id="uie.query",
            governance=base_governance,
            result_success=False,  # Changed!
            benefit_score=0.9,
            harm_score=0.1,
            previous_hash=None,
        )
        record3.record_hash = record3.compute_hash()

        assert record1.record_hash != record3.record_hash, \
            "Different records must produce different hashes"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
