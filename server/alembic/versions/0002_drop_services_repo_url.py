"""drop repo_url from services

Revision ID: 0002_drop_services_repo_url
Revises: 0001_opscopilot_mvp_schema
Create Date: 2026-03-10 22:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_drop_services_repo_url"
down_revision: str | None = "0001_opscopilot_mvp_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("services", "repo_url")


def downgrade() -> None:
    op.add_column("services", sa.Column("repo_url", sa.String(length=300), nullable=True))
