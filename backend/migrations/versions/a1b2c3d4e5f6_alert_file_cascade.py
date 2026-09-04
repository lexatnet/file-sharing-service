"""alert file ondelete cascade

Revision ID: a1b2c3d4e5f6
Revises: 0d6439d2e79f
Create Date: 2026-09-02 00:00:00.000000

Deleting a file used to fail with an IntegrityError when it had alerts,
because the alerts.file_id FK had no ON DELETE action. Add CASCADE so the
database removes alerts together with their file.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '0d6439d2e79f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ON DELETE CASCADE to the alerts.file_id FK."""
    op.drop_constraint('alerts_file_id_fkey', 'alerts', type_='foreignkey')
    op.create_foreign_key(
        'alerts_file_id_fkey', 'alerts', 'files', ['file_id'], ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Restore the original FK without cascade."""
    op.drop_constraint('alerts_file_id_fkey', 'alerts', type_='foreignkey')
    op.create_foreign_key('alerts_file_id_fkey', 'alerts', 'files', ['file_id'], ['id'])
