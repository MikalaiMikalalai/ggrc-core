# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""Tests for TaskGroup import."""

import datetime
import collections

import ddt

from ggrc import db
from ggrc.converters import errors
from ggrc.models import all_models
from ggrc_workflows import models
from integration.ggrc.models import factories
from integration.ggrc_workflows.helpers.workflow_test_case \
    import WorkflowTestCase
from integration.ggrc_workflows.models import factories as wf_factories


@ddt.ddt
class TestTaskGroupImport(WorkflowTestCase):
  """Tests related to TaskGroup import."""

  WF_SLUG = "WORKFLOW-1"
  TG_SLUG = "TASKGROUP-1"

  def setUp(self):
    super(TestTaskGroupImport, self).setUp()
    with factories.single_commit():
      workflow = wf_factories.WorkflowFactory(slug=self.WF_SLUG)
      task_group = wf_factories.TaskGroupFactory(
          slug=self.TG_SLUG,
          workflow=workflow
      )
      wf_factories.TaskGroupTaskFactory(task_group=task_group)
      factories.PersonFactory(email="valid_user@example.com")

  @ddt.data(
      ("valid_user@example.com\nuser1@example.com",
       [errors.MULTIPLE_ASSIGNEES.format(line=3, column_name="Assignee")]),
      ("valid_user@example.com", []),
  )
  @ddt.unpack
  def test_import_assignee(self, assignee, expected_warnings):
    """Tests Assignee imported and set correctly for Task Group."""
    data = collections.OrderedDict([
        ("object_type", "TaskGroup"),
        ("code", self.TG_SLUG),
        ("workflow", self.WF_SLUG),
        ("Assignee", assignee)
    ])

    response = self.import_data(data)

    expected_messages = {
        "Task Group": {
            "row_warnings": set(expected_warnings),
        },
    }
    self._check_csv_response(response, expected_messages)
    task_group = all_models.TaskGroup.query.one()
    self.assertEqual(task_group.contact.email, "valid_user@example.com")

  @ddt.data(
      ("user1@example.com", [],
       [errors.NO_VALID_USERS_ERROR.format(line=3, column_name="Assignee")]),
      ("user2@example.com\nuser1@example.com",
       [errors.MULTIPLE_ASSIGNEES.format(line=3, column_name="Assignee")],
       [errors.NO_VALID_USERS_ERROR.format(line=3, column_name="Assignee")]),
      ("", [], [errors.MISSING_VALUE_ERROR.format(line=3,
                                                  column_name="Assignee")]),
  )
  @ddt.unpack
  def test_import_invalid_assignee(self,
                                   assignee,
                                   expected_warnings,
                                   expected_errors):
    """Tests Assignee import failed for Task Group."""
    data = collections.OrderedDict([
        ("object_type", "TaskGroup"),
        ("code", self.TG_SLUG),
        ("workflow", self.WF_SLUG),
        ("Assignee", assignee)
    ])
    response = self.import_data(data)
    expected_messages = {
        "Task Group": {
            "row_warnings": set(expected_warnings),
            "row_errors": set(expected_errors),
        },
    }
    self._check_csv_response(response, expected_messages)
    task_group = all_models.TaskGroup.query.one()
    self.assertFalse(task_group.contact)

  @ddt.data(
      (all_models.OrgGroup.__name__, "org group", True),
      (all_models.Vendor.__name__, "vendor", True),
      (all_models.AccessGroup.__name__, "access group", True),
      (all_models.System.__name__, "system", True),
      (all_models.Process.__name__, "process", True),
      (all_models.DataAsset.__name__, "data asset", True),
      (all_models.Product.__name__, "product", True),
      (all_models.Project.__name__, "project", True),
      (all_models.Facility.__name__, "facility", True),
      (all_models.Market.__name__, "market", True),
      (all_models.Program.__name__, "program", True),
      (all_models.Regulation.__name__, "regulation", True),
      (all_models.Policy.__name__, "policy", True),
      (all_models.Standard.__name__, "standard", True),
      (all_models.Contract.__name__, "contract", True),
      (all_models.Requirement.__name__, "requirement", True),
      (all_models.Control.__name__, "control", True),
      (all_models.Objective.__name__, "objective", True),
      (all_models.Issue.__name__, "issue", True),
      (all_models.Risk.__name__, "risk", True),
      (all_models.Threat.__name__, "threat", True),
      (all_models.Assessment.__name__, "assessment", False),
      (all_models.Audit.__name__, "audit", False),
      (all_models.Metric.__name__, "metric", True),
      (all_models.ProductGroup.__name__, "product group", True),
      (all_models.TechnologyEnvironment.__name__,
       "technology environment", True),
      (all_models.KeyReport.__name__, "key report", True),
  )
  @ddt.unpack
  def test_task_group_import_objects(self, model_name, header_name, is_mapped):
    """"Tests import TaskGroup with mapping to object: {0}."""

    mapped_slug = "MAPPEDOBJECT-1"
    with factories.single_commit():
      factories.get_model_factory(model_name)(slug=mapped_slug)

    tg_data = collections.OrderedDict([
        ("object_type", all_models.TaskGroup.__name__),
        ("code", self.TG_SLUG),
        ("workflow", self.WF_SLUG),
        ("map:{}".format(header_name), "{}".format(mapped_slug))
    ])
    result = self.import_data(tg_data)
    task_group = all_models.TaskGroup.query.one()
    mapped_objs = filter(lambda obj: obj.__class__.__name__ == model_name,
                         task_group.related_objects())
    if is_mapped:
      self.assertEqual(len(mapped_objs), 1)
      self.assertEqual(mapped_objs.pop().slug,
                       mapped_slug)
      self.assertEqual(len(result[0]['row_warnings']), 0)
    else:
      self.assertEqual(len(mapped_objs), 0)
      self.assertEqual(len(result[0]['block_warnings']), 1)
      self.assertEqual(
          result[0]['block_warnings'][0],
          errors.INVALID_TASKGROUP_MAPPING_WARNING.format(
              line=2, header_name=header_name
          )
      )

  def test_tgs_with_existing_slugs(self):
    """Tests import of task group with existing slug.

    When task groups with existing slugs are imported
    they shouldn't be unmapped from the previous workflow.
    Proper error should be displayed.
    """

    second_wf_slug = "WORKFLOW-2"
    wf_factories.WorkflowFactory(slug=second_wf_slug)

    second_tg_data = collections.OrderedDict([
        ("object_type", all_models.TaskGroup.__name__),
        ("code", self.TG_SLUG),
        ("workflow", second_wf_slug)
    ])
    response = self.import_data(second_tg_data)

    expected_error = errors.TASKGROUP_MAPPED_TO_ANOTHER_WORKFLOW.format(
        line=3,
        slug=self.TG_SLUG,
    )

    self.assertEquals([expected_error], response[0]['row_errors'])

    first_wf = db.session.query(models.Workflow).filter(
        models.Workflow.slug == self.WF_SLUG
    ).one()
    second_wf = db.session.query(models.Workflow).filter(
        models.Workflow.slug == second_wf_slug
    ).one()

    self.assertEqual(db.session.query(models.TaskGroup).filter(
        models.TaskGroup.workflow_id == first_wf.id).count(), 1)
    self.assertEqual(db.session.query(models.TaskGroup).filter(
        models.TaskGroup.workflow_id == second_wf.id).count(), 0)


@ddt.ddt
class TestTaskGroupTaskImport(WorkflowTestCase):
  """Tests related to TaskGroupTask import."""

  def setUp(self):
    super(TestTaskGroupTaskImport, self).setUp()
    self.person = factories.PersonFactory()
    self.workflow = wf_factories.WorkflowFactory(repeat_every=7,
                                                 unit=models.Workflow.DAY_UNIT)
    self.task_group = wf_factories.TaskGroupFactory(workflow=self.workflow)

  @ddt.data(
      (datetime.date(2018, 7, 13), datetime.date(2018, 7, 21),
       {u"Line 3: Task Due Date can not occur on weekends."}),
      (datetime.date(2018, 7, 14), datetime.date(2018, 7, 20),
       {u"Line 3: Task Start Date can not occur on weekends."}),
      (datetime.date(2018, 7, 14), datetime.date(2018, 7, 21),
       {u"Line 3: Task Due Date can not occur on weekends.",
        u"Line 3: Task Start Date can not occur on weekends."})
  )
  @ddt.unpack
  def test_task_group_task_weekend(self, start_date, end_date,
                                   expected_errors):
    """Tests TaskGroupTask import can't start/end on weekends."""

    tgt_data = collections.OrderedDict([
        ("object_type", "Task Group Task"),
        ("code", "TASKGROUPTASK-1"),
        ("task type", "Rich Text"),
        ("task group", self.task_group.slug),
        ("summary", "Task group test task 1"),
        ("start date", start_date),
        ("end date", end_date),
        ("task assignees", self.person.email),
    ])

    object_count_before_import = all_models.TaskGroupTask.query.count()
    response = self.import_data(tgt_data)

    expected_messages = {
        "Task Group Task": {
            "row_errors": expected_errors,
        }
    }

    object_count_after_import = all_models.TaskGroupTask.query.count()
    self._check_csv_response(response, expected_messages)
    self.assertEqual(object_count_before_import, object_count_after_import)

  @ddt.data((datetime.date(2018, 7, 10), datetime.date(2018, 7, 21),
             {u"Line 3: Task Due Date can not occur on weekends."}),
            (datetime.date(2018, 7, 14), datetime.date(2018, 7, 17),
             {u"Line 3: Task Start Date can not occur on weekends."}),
            (datetime.date(2018, 7, 14), datetime.date(2018, 7, 21),
             {u"Line 3: Task Due Date can not occur on weekends.",
              u"Line 3: Task Start Date can not occur on weekends."})
            )
  @ddt.unpack
  def test_import_change_task_date(self, start_date, end_date,
                                   expected_errors):
    """Tests import can't change start/end from weekdays to weekends."""

    wf_factories.TaskGroupTaskFactory(
        task_group=self.task_group,
        start_date=datetime.date(2018, 7, 10),
        end_date=datetime.date(2018, 7, 17),
    )

    task_group_task_before = db.session.query(models.TaskGroupTask).one()

    start_date_before = task_group_task_before.start_date
    end_date_before = task_group_task_before.end_date

    tgt_import_data = collections.OrderedDict([
        ("object_type", "Task Group Task"),
        ("code", task_group_task_before.slug),
        ("task type", "Rich Text"),
        ("task group", self.task_group.slug),
        ("summary", "Task group test task 1"),
        ("start date", start_date),
        ("end date", end_date),
        ("task assignees", self.person.email),
    ])

    response = self.import_data(tgt_import_data)

    task_group_task_after = db.session.query(models.TaskGroupTask).one()

    start_date_after = task_group_task_after.start_date
    end_date_after = task_group_task_after.end_date

    expected_messages = {
        "Task Group Task": {
            "row_errors": expected_errors,
        }
    }

    self._check_csv_response(response, expected_messages)
    self.assertEquals(start_date_before, start_date_after)
    self.assertEquals(end_date_before, end_date_after)
