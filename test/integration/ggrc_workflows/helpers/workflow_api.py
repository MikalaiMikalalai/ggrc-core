# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""Package contains Workflow related helper functions for REST API calls."""

from ggrc import utils
from ggrc.app import app
from ggrc.access_control import role
from ggrc.models import all_models

from integration.ggrc.models import factories


def _get_acl_subdict(acr_name, person, model):
  """Generate ACL sub-dict representation for using inside JSON.

  Args:
      acr_name: Access Control Role name.
      person: Person instance, who should get `acr_name` in scope of `model`.
      model: Model, in which scope ACR should be assigned to `person`.
  Returns:
      ACL entry sub-dict representation. It is used for inserting into object
      JSON representation under 'access_control_list' key.
  """
  with app.app_context():
    acr = role.get_ac_roles_for(model.__name__)[acr_name]
    return {
        "ac_role_id": acr.id,
        "person": utils.create_stub(person)
    }


def get_task_group_post_dict(workflow, contact):
  """Get TaskGroup JSON representation for POST API call.

  Args:
      workflow: Workflow instance which TaskGroup should belong to.
      contact: Person instance which should become TaskGroup Assignee.
  Returns:
      TaskGroup object dict representation for using in POST request.
  """
  return {
      "task_group": {
          "custom_attributes": {},
          "contact": utils.create_stub(contact),
          "workflow": utils.create_stub(workflow),
          "context": utils.create_stub(workflow.context),
          "modal_title": "Create Task Group",
          "title": factories.random_str(prefix="tg_"),
          "description": factories.random_str(length=64),
          "slug": "",
      }
  }


def get_task_post_dict(task_group, people_roles, start_date, end_date):
  """Get TaskGroupTask JSON representation for POST API call.

  Args:
      task_group: TaskGroup instance which TaskGroupTask should belong to.
      people_roles: Mapping like {'ACR name': Person instance}
      start_date: String date representation.
      end_date: String date representation.
  Returns:
      TaskGroupTask object dict representation for using in POST request.
  """
  response = {
      "task_group_task": {
          "response_options": [],
          "start_date": start_date,
          "end_date": end_date,
          "access_control_list": [],
          "custom_attributes": {},
          "task_group": utils.create_stub(task_group),
          "context": utils.create_stub(task_group.context),
          "modal_title": "Create New Task",
          "title": factories.random_str(prefix="tgt_"),
          "task_type": "text",
          "description": factories.random_str(length=64),
          "slug": ""
      }
  }

  for acr_name, person in people_roles.iteritems():
    response["task_group_task"]["access_control_list"].append(
        _get_acl_subdict(acr_name, person, all_models.TaskGroupTask)
    )
  return response


def get_cycle_post_dict(workflow):
  """Get Cycle JSON representation for POST API call.

  Args:
      workflow: Workflow instance which Cycle should belong to.
  Returns:
      Cycle object dict representation for using in POST request.
  """
  return {
      "cycle": {
          "context": utils.create_stub(workflow.context),
          "workflow": utils.create_stub(workflow),
          "autogenerate": True,
          "isOverdue": False
      }
  }


def get_cycle_task_entry_post_dict(cycle_task):
  """Get CycleTaskEntry JSON representation for POST API call.

  Args:
      cycle_task: CycleTaskGroupObjectTask instance which CycleTaskEntry
          should belong to.
  Returns:
      CycleTaskEntry object dict representation for using in POST request.
  """
  return {
      "cycle_task_entry": {
          "custom_attributes": {},
          "cycle_task_group_object_task": utils.create_stub(cycle_task),
          "cycle": utils.create_stub(cycle_task.cycle),
          "context": utils.create_stub(cycle_task.context),
          "is_declining_review": "",
          "description": factories.random_str(length=64),
      }
  }


def get_task_group_clone_dict(source_task_group, clone_objects=False,
                              clone_tasks=False, clone_people=False):
  """Get TaskGroup JSON for clone operation for POST API call.

  Args:
      source_task_group: Source TaskGroup instance.
      clone_objects: Shows is mapped objects should be cloned.
      clone_tasks: Shows is related tasks should be cloned.
      clone_people: Shows is assigned people should be cloned.
  Returns:
      TaskGroup clone operation representation for using in POST request.
  """
  return {
      "task_group": {
          "clone": source_task_group.id,
          "context": None,
          "clone_objects": clone_objects,
          "clone_tasks": clone_tasks,
          "clone_people": clone_people,
      }
  }
