"""patch waifu

迁移 ID: 782cb0785d08
父迁移: 4d78f4f6c5fa
创建时间: 2025-06-19 11:14:03.383734

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "782cb0785d08"
down_revision: str | Sequence[str] | None = "4d78f4f6c5fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade(name: str = "") -> None:
    if name:
        return
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "yinpa_active",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("active_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_yinpa_active")),
        info={"bind_key": "waifu"},
    )
    op.create_table(
        "yinpa_passive",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("passive_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_yinpa_passive")),
        info={"bind_key": "waifu"},
    )
    # ### end Alembic commands ###


def downgrade(name: str = "") -> None:
    if name:
        return
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("yinpa_passive")
    op.drop_table("yinpa_active")
    # ### end Alembic commands ###
