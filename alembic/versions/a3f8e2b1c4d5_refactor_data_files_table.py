"""refactor_data_files_table

Revision ID: a3f8e2b1c4d5
Revises: 59467ea1b81e
Create Date: 2026-03-06

"""

from typing import Union, Sequence

import sqlalchemy as sa

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "a3f8e2b1c4d5"
down_revision: Union[str, Sequence[str], None] = "59467ea1b81e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Drop old data_files table
    op.drop_index("ix_data_files_data_type", table_name="data_files")
    op.drop_index("ix_data_files_id", table_name="data_files")
    op.drop_index("ix_data_files_station", table_name="data_files")
    op.drop_table("data_files")

    # Create data_types table
    op.create_table(
        "data_types",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_data_types_id"), "data_types", ["id"], unique=False)

    # Create stations table
    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_stations_id"), "stations", ["id"], unique=False)

    # Create files table
    op.create_table(
        "files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type_code", sa.String(), nullable=False),
        sa.Column("station_code", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("file_sha256", sa.String(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("date", sa.Date(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["type_code"], ["data_types.code"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["station_code"], ["stations.code"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_path"),
    )
    op.create_index(op.f("ix_files_id"), "files", ["id"], unique=False)
    op.create_index(op.f("ix_files_type_code"), "files", ["type_code"], unique=False)
    op.create_index(
        op.f("ix_files_station_code"), "files", ["station_code"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_files_station_code", table_name="files")
    op.drop_index("ix_files_type_code", table_name="files")
    op.drop_index("ix_files_id", table_name="files")
    op.drop_table("files")

    op.drop_index("ix_stations_id", table_name="stations")
    op.drop_table("stations")

    op.drop_index("ix_data_types_id", table_name="data_types")
    op.drop_table("data_types")

    # Recreate original data_files table
    op.create_table(
        "data_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("data_type", sa.String(), nullable=False),
        sa.Column("station", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("file_sha256", sa.String(), nullable=False),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("total_rows", sa.Integer(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("file_path"),
    )
    op.create_index(
        op.f("ix_data_files_data_type"), "data_files", ["data_type"], unique=False
    )
    op.create_index(op.f("ix_data_files_id"), "data_files", ["id"], unique=False)
    op.create_index(
        op.f("ix_data_files_station"), "data_files", ["station"], unique=False
    )
