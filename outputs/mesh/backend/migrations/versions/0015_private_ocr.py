"""Private encrypted OCR suggestions with leased processing; never automatic approval."""

import sqlalchemy as sa
from alembic import op

revision = "0015"
down_revision = "0014"


def upgrade():
    op.add_column(
        "identity_documents",
        sa.Column("ocr_status", sa.String(30), nullable=False, server_default="not_configured"),
    )
    op.add_column(
        "identity_documents",
        sa.Column("ocr_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("identity_documents", sa.Column("ocr_lease_until", sa.DateTime(timezone=True)))
    op.add_column("identity_documents", sa.Column("ocr_ciphertext", sa.Text()))
    op.add_column("identity_documents", sa.Column("ocr_error_code", sa.String(60)))
    op.add_column("identity_documents", sa.Column("ocr_completed_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_identity_ocr_queue",
        "identity_documents",
        ["organization_id", "ocr_status", "ocr_lease_until"],
    )


def downgrade():
    op.drop_index("ix_identity_ocr_queue", table_name="identity_documents")
    for name in (
        "ocr_completed_at",
        "ocr_error_code",
        "ocr_ciphertext",
        "ocr_lease_until",
        "ocr_attempts",
        "ocr_status",
    ):
        op.drop_column("identity_documents", name)
