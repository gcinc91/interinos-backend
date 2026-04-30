"""init

Revision ID: 0001_init
Revises:
Create Date: 2026-05-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "0001_init"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "vacancies",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("source_id", sa.String, nullable=False, unique=True),
        sa.Column("cuerpo", sa.String, nullable=False),
        sa.Column("especialidad", sa.String, nullable=True),
        sa.Column("centro", sa.String, nullable=False),
        sa.Column("centro_codigo", sa.String, nullable=True),
        sa.Column("puesto_codigo", sa.String, nullable=True),
        sa.Column("localidad", sa.String, nullable=True),
        sa.Column("provincia", sa.String, nullable=True),
        sa.Column("tipo", sa.String, nullable=True),
        sa.Column("participacion", sa.String, nullable=True),
        sa.Column("observaciones", sa.Text, nullable=True),
        sa.Column("fecha_cese", sa.DateTime(timezone=True), nullable=True),
        sa.Column("geom", Geography(geometry_type="POINT", srid=4326), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False),
        sa.Column("content_hash", sa.String, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("vacancies_geom_gix", "vacancies", ["geom"], postgresql_using="gist")
    op.create_index("vacancies_active_idx", "vacancies", ["is_active"])
    op.create_index("vacancies_cuerpo_idx", "vacancies", ["cuerpo", "especialidad"])

    op.create_table(
        "scrape_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("items_inserted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("items_updated", sa.Integer, nullable=False, server_default="0"),
        sa.Column("items_removed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("data_version", sa.String, nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
    )

    op.create_table(
        "geocode_cache",
        sa.Column("address_norm", sa.String, primary_key=True),
        sa.Column("lat", sa.Float, nullable=False),
        sa.Column("lon", sa.Float, nullable=False),
        sa.Column("provider", sa.String, nullable=False, server_default="nominatim"),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "distance_cache",
        sa.Column("origin_lat", sa.Float, primary_key=True),
        sa.Column("origin_lon", sa.Float, primary_key=True),
        sa.Column("dest_lat", sa.Float, primary_key=True),
        sa.Column("dest_lon", sa.Float, primary_key=True),
        sa.Column("road_distance_m", sa.Integer, nullable=True),
        sa.Column("road_duration_s", sa.Integer, nullable=True),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("distance_cache")
    op.drop_table("geocode_cache")
    op.drop_table("scrape_runs")
    op.drop_index("vacancies_cuerpo_idx", table_name="vacancies")
    op.drop_index("vacancies_active_idx", table_name="vacancies")
    op.drop_index("vacancies_geom_gix", table_name="vacancies")
    op.drop_table("vacancies")
