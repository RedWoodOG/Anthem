"""initial_schema

Revision ID: 9d3a9d81d129
Revises: 
Create Date: 2026-05-15 21:02:00.090852

"""
from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '9d3a9d81d129'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("tenant_id", sa.String(128), nullable=False, default="default"),
        sa.Column("permissions", sa.JSON(), nullable=False, default=list),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False, default=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("request_id", sa.String(64), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(128), nullable=False),
        sa.Column("actor", sa.String(128), nullable=False),
        sa.Column("capability_id", sa.String(256), nullable=False),
        sa.Column("governance_tier", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("prior_hash", sa.String(64), nullable=True),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
    )

    op.create_table(
        "agent_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(64), nullable=False, index=True),
        sa.Column("task", sa.String(128), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("tokens_used", sa.Integer(), nullable=False, default=0),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
    )

    op.create_table(
        "drift_metrics",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(64), nullable=False, index=True),
        sa.Column("metric_name", sa.String(64), nullable=False),
        sa.Column("baseline_value", sa.Float(), nullable=False),
        sa.Column("current_value", sa.Float(), nullable=False),
        sa.Column("drift_std", sa.Float(), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_id", sa.String(64), nullable=False, index=True),
        sa.Column("task", sa.String(256), nullable=False),
        sa.Column("expected_outcome", sa.JSON(), nullable=True),
        sa.Column("actual_outcome", sa.JSON(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_by", sa.String(128), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("drift_metrics")
    op.drop_table("agent_events")
    op.drop_table("audit_log")
    op.drop_table("api_keys")
