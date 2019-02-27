# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Audit RBAC Factory."""
from ggrc.models import all_models
from integration.ggrc import Api
from integration.ggrc.models import factories
from integration.ggrc_workflows.models import factories as wf_factories


class BaseRBACFactory(object):
  """Base RBAC factory class."""
  # pylint: disable=too-many-instance-attributes

  def setup_program_scope(self, user_id, acr, parent=None):
    """Set up base set of objects for permission tests of Program scope models.

    Args:
        acr: Instance of ACR that should be assigned for tested user.
        parent: Model name in scope of which objects should be set up.
    """
    # pylint: disable=attribute-defined-outside-init
    with factories.single_commit():
      self.program = factories.ProgramFactory()
      self.program_id = self.program.id
      self.assign_person(self.program, acr, user_id)
      if parent == "Program":
        return
      self.audit = factories.AuditFactory(program=self.program)
      factories.RelationshipFactory(
          source=self.audit,
          destination=self.program,
      )
      self.audit_id = self.audit.id
      self.assign_person(self.audit, acr, user_id)
      if parent == "Audit":
        return
      self.assessment = factories.AssessmentFactory(audit=self.audit)
      self.assessment_id = self.assessment.id
      self.assign_person(self.assessment, acr, user_id)
      factories.RelationshipFactory(
          source=self.audit, destination=self.assessment
      )

  def setup_workflow_scope(self, user_id, acr):
    """Set up base set of objects for permission tests of Workflow models.

    Args:
        acr: Instance of ACR that should be assigned for tested user.
        parent: Model name in scope of which objects should be set up.
    """
    # pylint: disable=attribute-defined-outside-init
    acr_id = acr.id
    with factories.single_commit():
      self.workflow = wf_factories.WorkflowFactory()
      self.workflow_id = self.workflow.id
      self.assign_person(self.workflow, acr, user_id)

      self.task_group = wf_factories.TaskGroupFactory(workflow=self.workflow)
      self.task_group_id = self.task_group.id

      self.task = wf_factories.TaskGroupTaskFactory(task_group=self.task_group)
      self.task_id = self.task.id
      self.assign_person(self.task, acr, user_id)
    # import pdb; pdb.set_trace()
    self.generate_cycle(self.workflow_id)
    cycle_task = all_models.CycleTaskGroupObjectTask.query.first()
    self.cycle_task_id = cycle_task.id
    acr = all_models.AccessControlRole.query.get(acr_id)
    self.assign_person(cycle_task, acr, user_id)

  @staticmethod
  def generate_cycle(workflow_id, api=None):
    """Create cycle with task automatically."""
    if not api:
      api = Api()
    return api.post(all_models.Cycle, {
        "cycle": {
            "context": None,
            "autogenerate": True,
            "isOverdue": False,
            "workflow": {
                "id": workflow_id,
                "type": "Workflow",
            },
        }
    })

  @staticmethod
  def assign_person(object_, acr, person_id):
    """Assign person to object."""
    # pylint: disable=protected-access
    for ac_list in object_._access_control_list:
      if ac_list.ac_role.name == acr.name and acr.object_type == object_.type:
        factories.AccessControlPersonFactory(
            person_id=person_id,
            ac_list=ac_list,
        )
