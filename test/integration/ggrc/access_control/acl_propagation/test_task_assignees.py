# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Test Access Control roles Task Assignees propagation"""

import ddt

from ggrc.models import all_models
from integration.ggrc.access_control import rbac_factories
from integration.ggrc.access_control.acl_propagation import base
from integration.ggrc.utils import helpers


@ddt.ddt
class TestTaskAssigneesPropagation(base.TestACLPropagation):
  """Test Task Assignees role permissions propagation"""

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
              "read": True,
              "update": True,
              "delete": False,
              "read_revisions": (False, "unimplemented"),
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
              "read": (False, "unimplemented"),
              "update": (False, "unimplemented"),
              "delete": False,
              "add_comment": True,
              "read_comment": True,
              "map_control": False,
              "map_created_control": (False, "unimplemented"),
              "read_mapped_control": False,
              "upmap_control": False,
              "start": (False, "unimplemented"),
              "end": (False, "unimplemented"),
              "verify": (False, "unimplemented"),
              "decline": (False, "unimplemented"),
              "restore": (False, "unimplemented"),
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
              "update": True,
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
              "update": (False, "unimplemented"),
              "delete": False,
              "add_comment": True,
              "read_comment": True,
              "map_control": False,
              "map_created_control": (False, "unimplemented"),
              "read_mapped_control": True,
              "upmap_control": False,
              "start": (False, "unimplemented"),
              "end": (False, "unimplemented"),
              "verify": (False, "unimplemented"),
              "decline": (False, "unimplemented"),
              "restore": (False, "unimplemented"),
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
    """Initialize RBAC factory with propagated Task Assignees role.

    Args:
        role: Global Custom role that user have (Creator/Reader/Editor).
        model: Model name for which factory should be got.
        parent: Model name in scope of which objects should be installed.

    Returns:
        Initialized RBACFactory object.
    """
    self.setup_people()
    task_assignees_acr = all_models.AccessControlRole.query.filter_by(
        name="Task Assignees",
        object_type="TaskGroupTask",
    ).first()

    rbac_factory = rbac_factories.TEST_FACTORIES_MAPPING[model]
    return rbac_factory(self.people[role].id, task_assignees_acr, parent)

  @helpers.unwrap(PERMISSIONS)
  def test_access(self, role, model, action_name, expected_result):
    """Task Assignees {0:<7}: On {1:<20} test {2:<20} - Expected {3:<2} """
    self.runtest(role, model, action_name, expected_result)
