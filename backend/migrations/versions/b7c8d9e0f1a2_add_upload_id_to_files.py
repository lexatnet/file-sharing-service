"""add upload_id column to files

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-09-04 00:00:00.000000

Files are now uploaded to S3 as multipart uploads. The active S3 UploadId is
persisted on the row so an interrupted upload can be resumed (list/completed)
after a backend restart. Nullable: completed files leave it empty.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the (nullable) upload_id column."""
    op.add_column('files', sa.Column('upload_id', sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Drop upload_id."""
    op.drop_column('files', 'upload_id')