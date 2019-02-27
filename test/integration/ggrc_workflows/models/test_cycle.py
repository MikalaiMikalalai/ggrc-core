# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""Cycle model related tests."""

import ddt

from ggrc.models import all_models
from ggrc_workflows import ac_roles
from integration.ggrc.models import factories
from integration.ggrc_workflows.helpers import rbac_helper
from integration.ggrc_workflows.helpers import workflow_api
from integration.ggrc_workflows.helpers import workflow_test_case
from integration.ggrc_workflows.models import factories as wf_factories


@ddt.ddt
class TestCycleApiCalls(workflow_test_case.WorkflowTestCase):
  """Tests related to Cycle REST API calls."""

  @ddt.data(
      rbac_helper.GA_RNAME,
      rbac_helper.GE_RNAME,
      rbac_helper.GR_RNAME,
      rbac_helper.GC_RNAME,
  )
  def test_post_cycle_g_role_admin(self, g_rname):
    """Activate Workflow/POST Cycle logged in as {} & WF Admin."""
    with factories.single_commit():
      workflow = self.setup_helper.setup_workflow((g_rname,))
      task_group = wf_factories.TaskGroupFactory(workflow=workflow)
      wf_factories.TaskGroupTaskFactory(task_group=task_group)

    g_person = self.setup_helper.get_person(g_rname,
                                            ac_roles.workflow.ADMIN_NAME)
    self.api_helper.set_user(g_person)

    workflow = all_models.Workflow.query.one()

    data = workflow_api.get_cycle_post_dict(workflow)
    response = self.api_helper.post(all_models.Cycle, data)
    self.assertEqual(response.status_code, 201)

  def test_get_cycle_g_reader_no_role(self):
    """GET Cycle collection logged in as GlobalReader & No Role."""
    with factories.single_commit():
      wf_factories.CycleFactory()
      self.setup_helper.setup_person(rbac_helper.GR_RNAME, "No Role")

    g_reader = self.setup_helper.get_person(rbac_helper.GR_RNAME, "No Role")
    self.api_helper.set_user(g_reader)

    cycle = all_models.Cycle.query.one()
    response = self.api_helper.get_collection(cycle, (cycle.id, ))
    self.assertTrue(response.json["cycles_collection"]["cycles"])

  @ddt.data("Risk",
            "Control")
  def test_create_with_mapped_object(self, model_name):
    """Test cycle creation with mapped {0}."""
    with factories.single_commit():
      mapped_object = factories.get_model_factory(model_name)()
      task_group = wf_factories.TaskGroupFactory()
      wf_factories.TaskGroupTaskFactory(task_group=task_group)
      factories.RelationshipFactory(source=task_group,
                                    destination=mapped_object)
    mapped_object_id = mapped_object.id

    data = workflow_api.get_cycle_post_dict(task_group.workflow)

    response = self.api_helper.post(all_models.Cycle, data)
    self.assertEquals(response.status_code, 201)

    cycle_id = response.json.get("cycle", {}).get("id")
    cycle = all_models.Cycle.query.filter_by(id=cycle_id).first()
    mapped_objs = filter(
        lambda obj: obj.__class__.__name__ == model_name,
        cycle.cycle_task_groups[0].task_group.related_objects()
    )
    obj_id = mapped_objs.pop().id
    self.assertEquals(obj_id, mapped_object_id)
