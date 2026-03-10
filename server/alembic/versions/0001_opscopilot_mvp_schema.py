"""opscopilot mvp schema

Revision ID: 0001_opscopilot_mvp_schema
Revises:
Create Date: 2026-03-10 16:35:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_opscopilot_mvp_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column(
            "role",
            sa.String(length=50),
            nullable=False,
            server_default="operations_engineer",
        ),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "services",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("tier", sa.String(length=40), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("repo_url", sa.String(length=300), nullable=True),
        sa.Column("runbook_path", sa.String(length=300), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_services_owner_user_id", "services", ["owner_user_id"])

    op.create_table(
        "service_dependencies",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("depends_on_service_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["depends_on_service_id"], ["services.id"]),
        sa.UniqueConstraint(
            "service_id", "depends_on_service_id", name="uq_service_dependency_pair"
        ),
    )
    op.create_index("ix_service_dependencies_service_id", "service_dependencies", ["service_id"])
    op.create_index(
        "ix_service_dependencies_depends_on_service_id",
        "service_dependencies",
        ["depends_on_service_id"],
    )

    op.create_table(
        "incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_key", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("commander_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["commander_user_id"], ["users.id"]),
        sa.UniqueConstraint("incident_key"),
    )
    op.create_index("ix_incidents_incident_key", "incidents", ["incident_key"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_severity", "incidents", ["severity"])
    op.create_index("ix_incidents_started_at", "incidents", ["started_at"])
    op.create_index("ix_incidents_created_by_user_id", "incidents", ["created_by_user_id"])

    op.create_table(
        "incident_services",
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("impact_type", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.PrimaryKeyConstraint("incident_id", "service_id"),
    )
    op.create_index("ix_incident_services_incident_id", "incident_services", ["incident_id"])
    op.create_index("ix_incident_services_service_id", "incident_services", ["service_id"])

    op.create_table(
        "incident_tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
    )
    op.create_index("ix_incident_tags_incident_id", "incident_tags", ["incident_id"])
    op.create_index("ix_incident_tags_tag", "incident_tags", ["tag"])

    op.create_table(
        "incident_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("event_time", sa.DateTime(), nullable=False),
        sa.Column("metric_name", sa.String(length=120), nullable=True),
        sa.Column("metric_value", sa.Numeric(16, 4), nullable=True),
        sa.Column("event_text", sa.Text(), nullable=True),
        sa.Column("unit", sa.String(length=40), nullable=True),
        sa.Column("tags_json", sa.JSON(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
    )
    op.create_index("ix_incident_evidence_incident_id", "incident_evidence", ["incident_id"])
    op.create_index("ix_incident_evidence_service_id", "incident_evidence", ["service_id"])
    op.create_index("ix_incident_evidence_event_time", "incident_evidence", ["event_time"])

    op.create_table(
        "resolutions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("incident_id", sa.Integer(), nullable=False),
        sa.Column("resolution_summary", sa.Text(), nullable=False),
        sa.Column("root_cause", sa.Text(), nullable=False),
        sa.Column("actions_taken_json", sa.JSON(), nullable=True),
        sa.Column("resolved_by_user_id", sa.Integer(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
        sa.ForeignKeyConstraint(["resolved_by_user_id"], ["users.id"]),
    )
    op.create_index("ix_resolutions_incident_id", "resolutions", ["incident_id"])
    op.create_index("ix_resolutions_resolved_at", "resolutions", ["resolved_at"])
    op.create_index("ix_resolutions_resolved_by_user_id", "resolutions", ["resolved_by_user_id"])

    op.create_table(
        "escalation_contacts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("service_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("contact_type", sa.String(length=40), nullable=False),
        sa.Column("contact_value", sa.String(length=255), nullable=False),
        sa.Column("priority_order", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.UniqueConstraint(
            "service_id", "priority_order", name="uq_service_escalation_priority"
        ),
    )
    op.create_index("ix_escalation_contacts_service_id", "escalation_contacts", ["service_id"])

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("incident_id", sa.Integer(), nullable=True),
        sa.Column("session_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("last_activity_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index("ix_sessions_incident_id", "sessions", ["incident_id"])

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=False),
        sa.Column("structured_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index("ix_messages_created_at", "messages", ["created_at"])
    op.create_index(
        "ix_messages_session_id_created_at", "messages", ["session_id", "created_at"]
    )

    op.create_table(
        "investigation_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("evidence_type", sa.String(length=40), nullable=False),
        sa.Column("evidence_ref", sa.String(length=255), nullable=False),
        sa.Column("evidence_source_table", sa.String(length=120), nullable=False),
        sa.Column("evidence_row_id", sa.String(length=120), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"]),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"]),
    )
    op.create_index(
        "ix_investigation_evidence_session_id", "investigation_evidence", ["session_id"]
    )
    op.create_index(
        "ix_investigation_evidence_message_id", "investigation_evidence", ["message_id"]
    )

    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("replaced_by_token_id", sa.Uuid(), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["replaced_by_token_id"], ["refresh_tokens.id"]),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_refresh_tokens_expires_at", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_index("ix_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index("ix_investigation_evidence_message_id", table_name="investigation_evidence")
    op.drop_index("ix_investigation_evidence_session_id", table_name="investigation_evidence")
    op.drop_table("investigation_evidence")

    op.drop_index("ix_messages_session_id_created_at", table_name="messages")
    op.drop_index("ix_messages_created_at", table_name="messages")
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_sessions_incident_id", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_table("sessions")

    op.drop_index("ix_escalation_contacts_service_id", table_name="escalation_contacts")
    op.drop_table("escalation_contacts")

    op.drop_index("ix_resolutions_resolved_by_user_id", table_name="resolutions")
    op.drop_index("ix_resolutions_resolved_at", table_name="resolutions")
    op.drop_index("ix_resolutions_incident_id", table_name="resolutions")
    op.drop_table("resolutions")

    op.drop_index("ix_incident_evidence_event_time", table_name="incident_evidence")
    op.drop_index("ix_incident_evidence_service_id", table_name="incident_evidence")
    op.drop_index("ix_incident_evidence_incident_id", table_name="incident_evidence")
    op.drop_table("incident_evidence")

    op.drop_index("ix_incident_tags_tag", table_name="incident_tags")
    op.drop_index("ix_incident_tags_incident_id", table_name="incident_tags")
    op.drop_table("incident_tags")

    op.drop_index("ix_incident_services_service_id", table_name="incident_services")
    op.drop_index("ix_incident_services_incident_id", table_name="incident_services")
    op.drop_table("incident_services")

    op.drop_index("ix_incidents_created_by_user_id", table_name="incidents")
    op.drop_index("ix_incidents_started_at", table_name="incidents")
    op.drop_index("ix_incidents_severity", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_incident_key", table_name="incidents")
    op.drop_table("incidents")

    op.drop_index(
        "ix_service_dependencies_depends_on_service_id", table_name="service_dependencies"
    )
    op.drop_index("ix_service_dependencies_service_id", table_name="service_dependencies")
    op.drop_table("service_dependencies")

    op.drop_index("ix_services_owner_user_id", table_name="services")
    op.drop_table("services")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_username", table_name="users")
    op.drop_table("users")
