# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

from ggrc import db
from ggrc.models.relationship import Relationship
from ggrc_workflows.models import Cycle
from ggrc_workflows.models import CycleTaskGroup
from ggrc_workflows.models import CycleTaskGroupObjectTask as CycleTask
from ggrc_workflows.models import TaskGroup
from ggrc_workflows.models import TaskGroupTask
from ggrc_workflows.models import Workflow
from ggrc_workflows.models import WORKFLOW_OBJECT_TYPES


def tg_task(object_type, related_type, related_ids):
  """ relationships between Task Groups and Task Group Tasks """

  if object_type == "TaskGroup":
    return db.session.query(TaskGroupTask.task_group_id).filter(
        TaskGroupTask.id.in_(related_ids))
  else:
    return db.session.query(TaskGroupTask.id).filter(
        TaskGroupTask.task_group_id.in_(related_ids))


def cycle_workflow(object_type, related_type, related_ids):
  """ relationships between Workflows and Cycles """

  if object_type == "Workflow":
    return db.session.query(Cycle.workflow_id).filter(
        Cycle.id.in_(related_ids))
  else:
    return db.session.query(Cycle.id).filter(
        Cycle.workflow_id.in_(related_ids))


def workflow_tg(object_type, related_type, related_ids):
  """ relationships between Workflows and Task Groups """

  if object_type == "Workflow":
    return db.session.query(TaskGroup.workflow_id).filter(
        TaskGroup.id.in_(related_ids))
  else:
    return db.session.query(TaskGroup.id).filter(
        TaskGroup.workflow_id.in_(related_ids))


def workflow_tgt(object_type, related_type, related_ids):
  """ indirect relationships between Workflows and Tasks """

  if object_type == "Workflow":
    return db.session.query(TaskGroup.workflow_id).join(TaskGroupTask).filter(
        TaskGroupTask.id.in_(related_ids))
  else:
    return db.session.query(TaskGroupTask.id).join(TaskGroup).filter(
        TaskGroup.workflow_id.in_(related_ids))


def workflow_ctg(object_type, related_type, related_ids):
  """ indirect relationships between Workflows and Cycle Task Groups """

  if object_type == "Workflow":
    return db.session.query(Cycle.workflow_id).join(CycleTaskGroup).filter(
        CycleTaskGroup.id.in_(related_ids))
  else:
    return db.session.query(CycleTaskGroup.id).join(Cycle).filter(
        Cycle.workflow_id.in_(related_ids))


def workflow_ctgot(object_type, related_type, related_ids):
  """ indirect relationships between Workflows and Cycle Tasks """

  if object_type == "Workflow":
    return db.session.query(Cycle.workflow_id) \
        .join(CycleTaskGroup).join(CycleTask).filter(
            CycleTask.id.in_(related_ids))
  else:
    return db.session.query(CycleTask.id) \
        .join(CycleTaskGroup).join(Cycle).filter(
            Cycle.workflow_id.in_(related_ids))


def cycle_ctg(object_type, related_type, related_ids):
  """ relationships between Cycle and Cycle Task Group """

  if object_type == "Cycle":
    return db.session.query(CycleTaskGroup.cycle_id).filter(
        CycleTaskGroup.id.in_(related_ids))
  else:
    return db.session.query(CycleTaskGroup.id).filter(
        CycleTaskGroup.cycle_id.in_(related_ids))


def cycle_ctogt(object_type, related_type, related_ids):
  """ indirect relationships between Cycle and Cycle Task """

  if object_type == "Workflow":
    return db.session.query(Cycle.workflow_id) \
        .join(CycleTaskGroup).join(CycleTask).filter(
            CycleTask.id.in_(related_ids))
  else:
    return db.session.query(CycleTask.id) \
        .join(CycleTaskGroup).join(Cycle).filter(
            Cycle.workflow_id.in_(related_ids))


def ctg_ctgot(object_type, related_type, related_ids):
  """ relationships between Cycle Task Groups and Cycle Tasks """
  if object_type == "CycleTaskGroup":
    return db.session.query(CycleTask.cycle_task_group_id).filter(
        CycleTask.id.in_(related_ids))
  else:
    return db.session.query(CycleTask.id).filter(
        CycleTask.cycle_task_group_id.in_(related_ids))


def ctg_ctgo(object_type, related_type, related_ids):
  """ Indirect relationship helper between Cycle Task Groups and Objects

  Build a query to find indirectly related objects.

  Args:
      object_type: Type name (string) of the sought objects
      related_type: Type name (string) of the known objects
      related_ids: List of ids of the known objects
  Returns:
      A query object which finds the ids of objects (of type object_type) that
      are indirectly related to one of the related objects.
  """
  if object_type == "CycleTaskGroup":
    join_by_source_id = db.session.query(CycleTask.cycle_task_group_id) \
        .join(Relationship, CycleTask.id == Relationship.source_id) \
        .filter(
            Relationship.source_type == "CycleTaskGroupObjectTask",
            Relationship.destination_type == related_type,
            Relationship.destination_id.in_(related_ids))
    join_by_destination_id = db.session.query(CycleTask.cycle_task_group_id) \
        .join(Relationship, CycleTask.id == Relationship.destination_id) \
        .filter(
            Relationship.destination_type == "CycleTaskGroupObjectTask",
            Relationship.source_type == related_type,
            Relationship.source_id.in_(related_ids))
    return join_by_source_id.union(join_by_destination_id)
  else:
    join_by_source_id = db.session.query(Relationship.destination_id) \
        .join(CycleTask, CycleTask.id == Relationship.source_id) \
        .filter(
            CycleTask.cycle_task_group_id.in_(related_ids),
            Relationship.source_type == "CycleTaskGroupObjectTask",
            Relationship.destination_type == object_type)
    join_by_destination_id = db.session.query(Relationship.source_id) \
        .join(CycleTask, CycleTask.id == Relationship.destination_id) \
        .filter(
            CycleTask.cycle_task_group_id.in_(related_ids),
            Relationship.destination_type == "CycleTaskGroupObjectTask",
            Relationship.source_type == object_type)
    return join_by_source_id.union(join_by_destination_id)


def cycle_ctgo(object_type, related_type, related_ids):
  """ indirect relationships between Cycles and Objects mapped to CycleTask """
  if object_type == "Cycle":
    join_by_source_id = db.session.query(CycleTask.cycle_id) \
        .join(Relationship, CycleTask.id == Relationship.source_id) \
        .filter(
            Relationship.source_type == "CycleTaskGroupObjectTask",
            Relationship.destination_type == related_type,
            Relationship.destination_id.in_(related_ids))
    join_by_destination_id = db.session.query(CycleTask.cycle_id) \
        .join(Relationship, CycleTask.id == Relationship.destination_id) \
        .filter(
            Relationship.destination_type == "CycleTaskGroupObjectTask",
            Relationship.source_type == related_type,
            Relationship.source_id.in_(related_ids))
    return join_by_source_id.union(join_by_destination_id)
  else:
    join_by_source_id = db.session.query(Relationship.destination_id) \
        .join(CycleTask, CycleTask.id == Relationship.source_id) \
        .filter(
            CycleTask.cycle_id.in_(related_ids),
            Relationship.source_type == "CycleTaskGroupObjectTask",
            Relationship.destination_type == object_type)
    join_by_destination_id = db.session.query(Relationship.source_id) \
        .join(CycleTask, CycleTask.id == Relationship.destination_id) \
        .filter(
            CycleTask.cycle_id.in_(related_ids),
            Relationship.destination_type == "CycleTaskGroupObjectTask",
            Relationship.source_type == object_type)
    return join_by_source_id.union(join_by_destination_id)


def wf_ctgo(object_type, related_type, related_ids):
  """ indirect relationships between Workflows and Objects mapped to the
      Tasks in the Workflow.
  """
  if object_type == "Workflow":
    join_by_source_id = db.session.query(Workflow.id).join(
        Cycle, CycleTaskGroup, CycleTask) \
        .join(Relationship, CycleTask.id == Relationship.source_id) \
        .filter(
            Relationship.source_type == "CycleTaskGroupObjectTask",
            Relationship.destination_type == related_type,
            Relationship.destination_id.in_(related_ids))
    join_by_destination_id = db.session.query(Workflow.id).join(
        Cycle, CycleTaskGroup, CycleTask) \
        .join(Relationship, CycleTask.id == Relationship.destination_id) \
        .filter(
            Relationship.destination_type == "CycleTaskGroupObjectTask",
            Relationship.source_type == related_type,
            Relationship.source_id.in_(related_ids))
    return join_by_source_id.union(join_by_destination_id)
  else:
    join_by_source_id = db.session.query(Relationship.destination_id) \
        .join(CycleTask, CycleTask.id == Relationship.source_id) \
        .join(Cycle, Workflow) \
        .filter(
            Workflow.id.in_(related_ids),
            Relationship.source_type == "CycleTaskGroupObjectTask",
            Relationship.destination_type == object_type)
    join_by_destination_id = db.session.query(Relationship.source_id) \
        .join(CycleTask, CycleTask.id == Relationship.destination_id) \
        .join(Cycle, Workflow) \
        .filter(
            Workflow.id.in_(related_ids),
            Relationship.destination_type == "CycleTaskGroupObjectTask",
            Relationship.source_type == object_type)
    return join_by_source_id.union(join_by_destination_id)


_function_map = {
    ("Cycle", "CycleTaskGroup"): cycle_ctg,
    ("Cycle", "CycleTaskGroupObjectTask"): cycle_ctogt,
    ("Cycle", "Workflow"): cycle_workflow,
    ("CycleTaskGroup", "CycleTaskGroupObjectTask"): ctg_ctgot,
    ("CycleTaskGroup", "Workflow"): workflow_ctg,
    ("CycleTaskGroupObjectTask", "Workflow"): workflow_ctgot,
    ("TaskGroup", "TaskGroupTask"): tg_task,
    ("TaskGroup", "Workflow"): workflow_tg,
    ("TaskGroupTask", "Workflow"): workflow_tgt,
}

for wot in WORKFLOW_OBJECT_TYPES:
  for f, obj in [
          (ctg_ctgo, "CycleTaskGroup"),
          (cycle_ctgo, "Cycle"),
          (wf_ctgo, "Workflow")]:
    key = tuple(sorted([obj, wot]))
    _function_map[key] = f


def get_ids_related_to(object_type, related_type, related_ids):
  key = tuple(sorted([object_type, related_type]))
  query_function = _function_map.get(key)
  if callable(query_function):
    return query_function(object_type, related_type, related_ids)
  return None
