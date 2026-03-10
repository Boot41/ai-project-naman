"""move refresh token fields into users and drop refresh_tokens table

Revision ID: 0003_refresh_tokens_to_users
Revises: 0002_drop_services_repo_url
Create Date: 2026-03-10 23:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_refresh_tokens_to_users"
down_revision: str | None = "0002_drop_services_repo_url"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("refresh_token_hash", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("refresh_token_issued_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("refresh_token_expires_at", sa.DateTime(), nullable=True))
    op.add_column("users", sa.Column("refresh_token_revoked_at", sa.DateTime(), nullable=True))
    op.create_unique_constraint("uq_users_refresh_token_hash", "users", ["refresh_token_hash"])

    # Keep latest token state per user before dropping the old table.
    op.execute(
        """
        UPDATE users AS u
        SET
            refresh_token_hash = t.token_hash,
            refresh_token_issued_at = t.issued_at,
            refresh_token_expires_at = t.expires_at,
            refresh_token_revoked_at = t.revoked_at
        FROM (
            SELECT DISTINCT ON (user_id)
                user_id, token_hash, issued_at, expires_at, revoked_at
            FROM refresh_tokens
            ORDER BY user_id, issued_at DESC
        ) AS t
        WHERE u.id = t.user_id
        """
    )

    op.execute("DROP TABLE IF EXISTS refresh_tokens")


def downgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("replaced_by_token_id", sa.Uuid(), nullable=True),
        sa.Column("user_agent", sa.String(length=255), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["replaced_by_token_id"], ["refresh_tokens.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_index("ix_refresh_tokens_expires_at", "refresh_tokens", ["expires_at"])

    op.drop_constraint("uq_users_refresh_token_hash", "users", type_="unique")
    op.drop_column("users", "refresh_token_revoked_at")
    op.drop_column("users", "refresh_token_expires_at")
    op.drop_column("users", "refresh_token_issued_at")
    op.drop_column("users", "refresh_token_hash")
