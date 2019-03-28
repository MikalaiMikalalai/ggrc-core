# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""
Add new first-class attributes for Products, Systems, Processes:
'URL for Ariane' and 'URL for SPUR'

Create Date: 2019-03-28 12:30:23.572126
"""
# disable Invalid constant name pylint warning for mandatory Alembic variables.
# pylint: disable=invalid-name

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = 'acad4e4394c9'
down_revision = '2e4325bb21ed'


def upgrade():
  """Upgrade database schema and/or data, creating a new revision."""
  op.alter_column(
      "documents",
      "kind",
      existing_type=sa.Enum(u'FILE',
                            u'REFERENCE_URL'),
      existing_server_default=u'FILE',
      type_=sa.Enum(u'FILE',
                    u'REFERENCE_URL',
                    u'URL_FOR_ARIANE',
                    u'URL_FOR_SPUR'),
      server_default=u'REFERENCE_URL',
      nullable=False,
  )


def downgrade():
  """Downgrade database schema and/or data back to the previous revision."""
  raise NotImplementedError("Downgrade is not supported")
