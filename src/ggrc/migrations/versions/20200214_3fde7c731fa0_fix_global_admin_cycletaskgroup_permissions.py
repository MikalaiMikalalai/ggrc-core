# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""
Fix Global Admin/Editor CycleTaskGroup permissions.

Create Date: 2020-02-14 18:46:54.834982
"""
# disable Invalid constant name pylint warning for mandatory Alembic variables.
# pylint: disable=invalid-name

from ggrc.migrations.utils.acr_propagation import update_acr_propagation_tree
from ggrc.migrations.utils\
    import acr_propagation_constants_workflow_cycle_task_group\
    as acr_propagation_constants

# revision identifiers, used by Alembic.
revision = '3fde7c731fa0'
down_revision = '51cadec32665'


def upgrade():
  """Upgrade database schema and/or data, creating a new revision."""
  update_acr_propagation_tree(
      acr_propagation_constants.CURRENT_WORKFLOW_PROPAGATION,
      new_tree=acr_propagation_constants.WORKFLOW_PROPAGATION
  )


def downgrade():
  """Downgrade database schema and/or data back to the previous revision."""
  raise NotImplementedError("Downgrade is not supported")
