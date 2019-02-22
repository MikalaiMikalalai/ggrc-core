# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""
Workflow related generators
"""
import copy

from datetime import date

from ggrc import db
from ggrc import builder
from ggrc.access_control import role
from ggrc.models import Person
from ggrc_workflows.models import Cycle
from ggrc_workflows.models import TaskGroup
from ggrc_workflows.models import TaskGroupTask
from ggrc_workflows.models import Workflow
from integration.ggrc.access_control import acl_helper
from integration.ggrc.generator import Generator
from integration.ggrc.models import factories


class WorkflowsGenerator(Generator):
  """Workflow instances generator class."""

  def generate_workflow(self, data=None):
    """ create a workflow with dict data
    return: wf if it was created, or response otherwise
    """
    if data is None:
      data = {}
    obj_name = "workflow"
    data = copy.deepcopy(data)

    tgs = data.pop("task_groups", [])

    wf_instance = Workflow(title="wf " + factories.random_str())
    obj_dict = self.obj_to_dict(wf_instance, obj_name)
    wf_admin_role_id = {
        n: i
        for (i, n) in role.get_custom_roles_for(Workflow.__name__).iteritems()
    }['Admin']
    if "access_control_list" not in data:
      wf_admin_id = Person.query.first().id
      data["access_control_list"] = [
          acl_helper.get_acl_json(wf_admin_role_id, wf_admin_id)]
    obj_dict[obj_name].update(data)

    response, workflow = self.generate(Workflow, obj_name, obj_dict)

    for task_group in tgs:
      self.generate_task_group(workflow, task_group)

    return response, workflow

  def generate_task_group(self, workflow=None, data=None):
    """Generates task group over api."""
    if data is None:
      data = {}
    if not workflow:
      _, workflow = self.generate_workflow()
    data = copy.deepcopy(data)

    tgts = data.pop("task_group_tasks", [])

    obj_name = "task_group"
    workflow = self._session_add(workflow)
    wf_admin_id = Person.query.first().id
    task_group = TaskGroup(
        title="tg " + factories.random_str(),
        workflow_id=workflow.id,
        context_id=workflow.context.id,
        contact_id=wf_admin_id
    )
    obj_dict = self.obj_to_dict(task_group, obj_name)
    obj_dict[obj_name].update(data)

    response, task_group = self.generate(TaskGroup, obj_name, obj_dict)

    for tgt in tgts:
      self.generate_task_group_task(task_group, tgt)

    return response, task_group

  def generate_task_group_task(self, task_group=None, data=None):
    """Generate task group task over api."""
    if data is None:
      data = {}
    if not task_group:
      _, task_group = self.generate_task_group()
    task_group = self._session_add(task_group)

    default_start = self.random_date()
    default_end = self.random_date(default_start, date.today())
    obj_name = "task_group_task"
    cycle_task_role_id = {
        v: k for (k, v) in
        role.get_custom_roles_for("TaskGroupTask").iteritems()
    }['Task Assignees']
    tgt = TaskGroupTask(
        task_group_id=task_group.id,
        context_id=task_group.context.id,
        title="tgt " + factories.random_str(),
        start_date=default_start,
        end_date=default_end,
    )
    obj_dict = self.obj_to_dict(tgt, obj_name)
    if "access_control_list" not in data:
      wf_admin_id = Person.query.first().id
      data["access_control_list"] = [
          acl_helper.get_acl_json(cycle_task_role_id, wf_admin_id)]
    obj_dict[obj_name].update(data)
    return self.generate(TaskGroupTask, obj_name, obj_dict)

  def generate_cycle(self, workflow=None):
    """Generate Cycle over api."""
    if not workflow:
      _, workflow = self.generate_workflow()

    workflow = self._session_add(workflow)  # this should be nicer

    obj_name = "cycle"

    obj_dict = {
        obj_name: {
            "workflow": {
                "id": workflow.id,
                "type": workflow.__class__.__name__,
                "href": "/api/workflows/%d" % workflow.id
            },
            "context": {
                "id": workflow.context.id,
                "type": workflow.context.__class__.__name__,
                "href": "/api/workflows/%d" % workflow.context.id
            },
            "autogenerate": "true"
        }
    }

    return self.generate(Cycle, obj_name, obj_dict)

  def activate_workflow(self, workflow):
    """Activate workflow over api."""
    workflow = self._session_add(workflow)
    return self.modify_workflow(workflow, {
        "status": "Active",
        "recurrences": bool(workflow.repeat_every and workflow.unit)
    })

  def modify_workflow(self, wf_instance=None, data=None):
    """Modify workflow over api."""
    if data is None:
      data = {}
    if not wf_instance:
      _, wf_instance = self.generate_workflow()
    wf_instance = self._session_add(wf_instance)

    obj_name = "workflow"

    obj_dict = builder.json.publish(wf_instance)
    builder.json.publish_representation(obj_dict)
    obj_dict.update(data)

    default = {obj_name: obj_dict}

    response, workflow = self.modify(wf_instance, obj_name, default)

    return response, workflow

  def modify_object(self, obj, data=None):
    """Modify object over api."""
    if data is None:
      data = {}
    obj = self._session_add(obj)

    obj_name = obj._inflector.table_singular

    obj_dict = builder.json.publish(obj)
    builder.json.publish_representation(obj_dict)
    obj_dict.update(data)

    obj_data = {obj_name: obj_dict}

    response, generated_object = self.modify(obj, obj_name, obj_data)

    return response, generated_object

  @staticmethod
  def _session_add(obj):
    """ Sometimes tests throw conflicting state present error."""
    try:
      db.session.add(obj)
      return obj
    except:
      return obj.__class__.query.get(obj.id)
