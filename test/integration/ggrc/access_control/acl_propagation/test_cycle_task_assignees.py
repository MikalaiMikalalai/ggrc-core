# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Test Access Control roles Cycle Task Assignees propagation"""

import ddt

from ggrc.models import all_models
from integration.ggrc.access_control import rbac_factories
from integration.ggrc.access_control.acl_propagation import base
from integration.ggrc.utils import helpers


@ddt.ddt
class TestCycleTaskAssigneesPropagation(base.TestACLPropagation):
  """Test Cycle Task Assignees role permissions propagation"""

  PERMISSIONS = {
      "Creator": {
          "Workflow": {
              "read": False,
              "update": False,
              "delete": False,
              "read_revisions": False,
              "clone": False,
          },
          "TaskGroup": {
              "create": False,
              "read": False,
              "update": False,
              "delete": False,
              "read_revisions": False,
              "map_control": False,
              "map_created_control": False,
              "read_mapped_control": False,
              "upmap_control": False,
              "clone": False,
          },
          "TaskGroupTask": {
              "create": False,
              "read": False,
              "update": False,
              "delete": False,
              "read_revisions": False,
          },
          "Cycle": {
              "activate": False,
              "create": False,
              "read": False,
              "update": False,
              "delete": False,
              "end": False,
          },
          "CycleTaskGroup": {
              "read": False,
              "update": False,
              "delete": False,
          },
          "CycleTask": {
              "create": False,
              "read": True,
              "update": True,
              "delete": False,
              "add_comment": True,
              "read_comment": True,
              "map_control": False,
              "map_created_control": True,
              "read_mapped_control": False,
              "upmap_control": (True, "unimplemented"),
              "start": True,
              "end": True,
              "verify": True,
              "decline": True,
              "restore": True,
          },
      },
      "Reader": {
          "Workflow": {
              "read": True,
              "update": False,
              "delete": False,
              "read_revisions": True,
              "clone": (False, "unimplemented"),
          },
          "TaskGroup": {
              "create": False,
              "read": True,
              "update": False,
              "delete": False,
              "read_revisions": True,
              "map_control": False,
              "map_created_control": False,
              "read_mapped_control": True,
              "upmap_control": False,
              "clone": False,
          },
          "TaskGroupTask": {
              "create": False,
              "read": True,
              "update": False,
              "delete": False,
              "read_revisions": True,
          },
          "Cycle": {
              "activate": False,
              "create": False,
              "read": True,
              "update": False,
              "delete": False,
              "end": False,
          },
          "CycleTaskGroup": {
              "read": True,
              "update": False,
              "delete": False,
          },
          "CycleTask": {
              "create": False,
              "read": True,
              "update": True,
              "delete": False,
              "add_comment": True,
              "read_comment": True,
              "map_control": False,
              "map_created_control": True,
              "read_mapped_control": True,
              "upmap_control": (True, "unimplemented"),
              "start": True,
              "end": True,
              "verify": True,
              "decline": True,
              "restore": True,
          },
      },
      "Editor": {
          "Workflow": {
              "read": True,
              "update": True,
              "delete": True,
              "read_revisions": True,
              "clone": True,
          },
          "TaskGroup": {
              "create": True,
              "read": True,
              "update": True,
              "delete": True,
              "read_revisions": True,
              "map_control": True,
              "map_created_control": True,
              "read_mapped_control": True,
              "upmap_control": True,
              "clone": True,
          },
          "TaskGroupTask": {
              "create": True,
              "read": True,
              "update": True,
              "delete": True,
              "read_revisions": True,
          },
          "Cycle": {
              "activate": True,
              "create": True,
              "read": True,
              "update": False,
              "delete": False,
              "end": False,
          },
          "CycleTaskGroup": {
              "read": True,
              "update": False,
              "delete": False,
          },
          "CycleTask": {
              "create": True,
              "read": True,
              "update": True,
              "delete": False,
              "add_comment": True,
              "read_comment": True,
              "map_control": True,
              "map_created_control": True,
              "read_mapped_control": True,
              "upmap_control": True,
              "start": True,
              "end": True,
              "verify": True,
              "decline": True,
              "restore": True,
          },
      },
  }

  def init_factory(self, role, model, parent):
    """Initialize RBAC factory with propagated Cycle Task Assignees role.

    Args:
        role: Global Custom role that user have (Creator/Reader/Editor).
        model: Model name for which factory should be got.
        parent: Model name in scope of which objects should be installed.

    Returns:
        Initialized RBACFactory object.
    """
    self.setup_people()
    ctask_assignees_acr = all_models.AccessControlRole.query.filter_by(
        name="Task Assignees",
        object_type="CycleTaskGroupObjectTask",
    ).first()

    rbac_factory = rbac_factories.TEST_FACTORIES_MAPPING[model]
    return rbac_factory(self.people[role].id, ctask_assignees_acr, parent)

  @helpers.unwrap(PERMISSIONS)
  def test_access(self, role, model, action_name, expected_result):
    """Cycle Task Assignees {0:<7}: On {1:<21}test {2:<19}- Expected {3:<3}"""
    self.runtest(role, model, action_name, expected_result)
