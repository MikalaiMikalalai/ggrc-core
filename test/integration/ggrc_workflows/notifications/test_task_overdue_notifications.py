# -*- coding: utf-8 -*-

# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Integration tests for sending the notifications about overdue WF tasks."""

import unittest

import functools

from collections import OrderedDict
from datetime import date, datetime
from os.path import abspath, dirname, join

from freezegun import freeze_time
import ddt
from mock import patch

from ggrc import db, models
from ggrc.notifications import common
from ggrc_workflows.models import CycleTaskGroupObjectTask, Workflow

from integration.ggrc import TestCase

from integration.ggrc_workflows.generator import WorkflowsGenerator
from integration.ggrc.access_control import acl_helper
from integration.ggrc.api_helper import Api
from integration.ggrc.generator import ObjectGenerator


class TestTaskOverdueNotifications(TestCase):
  """Base class for task overdue notifications test suite."""

  def _fix_notification_init(self):
    """Fix Notification object init function.

    This is a fix needed for correct created_at field when using freezgun. By
    default the created_at field is left empty and filed by database, which
    uses system time and not the fake date set by freezugun plugin. This fix
    makes sure that object created in freeze_time block has all dates set with
    the correct date and time.
    """
    def init_decorator(init):
      """"Adjust the value of the object's created_at attribute to now."""
      @functools.wraps(init)
      def new_init(self, *args, **kwargs):
        init(self, *args, **kwargs)
        if hasattr(self, "created_at"):
          self.created_at = datetime.now()
      return new_init

    models.Notification.__init__ = init_decorator(models.Notification.__init__)


@ddt.ddt
class TestTaskOverdueNotificationsUsingAPI(TestTaskOverdueNotifications):
  """Tests for overdue notifications when changing Tasks with an API."""

  # pylint: disable=invalid-name

  def setUp(self):
    super(TestTaskOverdueNotificationsUsingAPI, self).setUp()
    self.api = Api()
    self.wf_generator = WorkflowsGenerator()
    self.object_generator = ObjectGenerator()
    models.Notification.query.delete()

    self._fix_notification_init()

    self.random_objects = self.object_generator.generate_random_objects(2)
    _, self.user = self.object_generator.generate_person(
        user_role="Administrator")
    self._create_test_cases()

  @ddt.data(True, False)
  @patch("ggrc.notifications.common.send_email")
  def test_sending_overdue_notifications_for_tasks(self, is_vf_needed, _):
    """Overdue notifications should be sent for overdue tasks every day.

    Even if an overdue notification has already been sent, it should still be
    sent in every following daily digest f a task is still overdue.
    """
    with freeze_time("2017-05-15 14:25:36"):
      tmp = self.one_time_workflow.copy()
      tmp['is_verification_needed'] = is_vf_needed
      _, workflow = self.wf_generator.generate_workflow(tmp)
      self.wf_generator.generate_cycle(workflow)
      response, workflow = self.wf_generator.activate_workflow(workflow)
      self.assert200(response)

    tasks = workflow.cycles[0].cycle_task_group_object_tasks
    task1_id = tasks[0].id
    task2_id = tasks[1].id

    user = models.Person.query.get(self.user.id)

    with freeze_time("2017-05-14 08:09:10"):
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertNotIn("task_overdue", user_notifs)

    with freeze_time("2017-05-15 08:09:10"):  # task 1 due date
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertNotIn("task_overdue", user_notifs)

    with freeze_time("2017-05-16 08:09:10"):  # task 2 due date
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertIn("task_overdue", user_notifs)

      overdue_task_ids = sorted(user_notifs["task_overdue"].keys())
      self.assertEqual(overdue_task_ids, [task1_id])

    with freeze_time("2017-05-17 08:09:10"):  # after both tasks' due dates
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertIn("task_overdue", user_notifs)

      overdue_task_ids = sorted(user_notifs["task_overdue"].keys())
      self.assertEqual(overdue_task_ids, [task1_id, task2_id])

      common.send_daily_digest_notifications()

    # even after sending the overdue notifications, they are sent again the
    # day after, too
    with freeze_time("2017-05-18 08:09:10"):
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertIn("task_overdue", user_notifs)

      overdue_task_ids = sorted(user_notifs["task_overdue"].keys())
      self.assertEqual(overdue_task_ids, [task1_id, task2_id])

  @ddt.data(True, False)
  @patch("ggrc.notifications.common.send_email")
  def test_adjust_overdue_notifications_on_task_due_date_change(self,
                                                                is_vf_needed,
                                                                _):
    """Sending overdue notifications should adjust to task due date changes."""
    with freeze_time("2017-05-15 14:25:36"):
      tmp = self.one_time_workflow.copy()
      tmp['is_verification_needed'] = is_vf_needed
      _, workflow = self.wf_generator.generate_workflow(tmp)
      self.wf_generator.generate_cycle(workflow)
      response, workflow = self.wf_generator.activate_workflow(workflow)
      self.assert200(response)

      tasks = workflow.cycles[0].cycle_task_group_object_tasks
      task1, task2 = tasks
      self.wf_generator.modify_object(task2, {"end_date": date(2099, 12, 31)})

      user = models.Person.query.get(self.user.id)

    with freeze_time("2017-05-16 08:09:10"):  # a day after task1 due date
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertIn("task_overdue", user_notifs)
      self.assertEqual(len(user_notifs["task_overdue"]), 1)

      # change task1 due date, there should be no overdue notification anymore
      self.wf_generator.modify_object(task1, {"end_date": date(2017, 5, 16)})
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertNotIn("task_overdue", user_notifs)

      # change task1 due date to the past there should a notification again
      self.wf_generator.modify_object(task1, {"end_date": date(2017, 5, 14)})
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertIn("task_overdue", user_notifs)
      self.assertEqual(len(user_notifs["task_overdue"]), 1)

  @ddt.data(True, False)
  @patch("ggrc.notifications.common.send_email")
  def test_adjust_overdue_notifications_on_task_status_change(self,
                                                              is_vf_needed,
                                                              _):
    """Sending overdue notifications should take task status into account."""
    with freeze_time("2017-05-15 14:25:36"):
      tmp = self.one_time_workflow.copy()
      tmp['is_verification_needed'] = is_vf_needed
      _, workflow = self.wf_generator.generate_workflow(tmp)
      self.wf_generator.generate_cycle(workflow)
      response, workflow = self.wf_generator.activate_workflow(workflow)
      self.assert200(response)

      tasks = workflow.cycles[0].cycle_task_group_object_tasks
      task1, task2 = tasks
      self.wf_generator.modify_object(task2, {"end_date": date(2099, 12, 31)})

      user = models.Person.query.get(self.user.id)
      user_email = user.email
    if is_vf_needed:
      non_final_states = [CycleTaskGroupObjectTask.ASSIGNED,
                          CycleTaskGroupObjectTask.IN_PROGRESS,
                          CycleTaskGroupObjectTask.FINISHED,
                          CycleTaskGroupObjectTask.DECLINED]
      final_state = CycleTaskGroupObjectTask.VERIFIED
    else:
      non_final_states = [CycleTaskGroupObjectTask.ASSIGNED,
                          CycleTaskGroupObjectTask.IN_PROGRESS]
      final_state = CycleTaskGroupObjectTask.FINISHED

    with freeze_time("2017-05-16 08:09:10"):  # a day after task1 due date
      for state in non_final_states:
        # clear all notifications before before changing the task status
        models.Notification.query.delete()
        _, notif_data = common.get_daily_notifications()
        self.assertEqual(notif_data, {})

        self.wf_generator.modify_object(task1, {"status": state})

        _, notif_data = common.get_daily_notifications()
        user_notifs = notif_data.get(user_email, {})
        self.assertIn("task_overdue", user_notifs)
        self.assertEqual(len(user_notifs["task_overdue"]), 1)

      # WITHOUT clearing the overdue notifications, move the task to "verified"
      # state, and the overdue notification should disappear.

      self.wf_generator.modify_object(task1, {"status": final_state})
      common.generate_cycle_tasks_notifs()
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user_email, {})
      self.assertNotIn("task_overdue", user_notifs)

  @ddt.data(True, False)
  @patch("ggrc.notifications.common.send_email")
  def test_stop_sending_overdue_notification_if_task_gets_deleted(self,
                                                                  is_vf_needed,
                                                                  _):
    """Overdue notifications should not be sent for deleted tasks."""
    with freeze_time("2017-05-15 14:25:36"):
      tmp = self.one_time_workflow.copy()
      tmp['is_verification_needed'] = is_vf_needed
      _, workflow = self.wf_generator.generate_workflow(tmp)
      self.wf_generator.generate_cycle(workflow)
      response, workflow = self.wf_generator.activate_workflow(workflow)
      self.assert200(response)

    tasks = workflow.cycles[0].cycle_task_group_object_tasks
    task1, task2 = tasks

    user = models.Person.query.get(self.user.id)
    user_email = user.email

    with freeze_time("2017-10-16 08:09:10"):  # long after both task due dates
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user_email, {})
      self.assertIn("task_overdue", user_notifs)
      self.assertEqual(len(user_notifs["task_overdue"]), 2)

      db.session.delete(task2)
      db.session.commit()

      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user_email, {})
      self.assertIn("task_overdue", user_notifs)
      self.assertEqual(len(user_notifs["task_overdue"]), 1)

      db.session.delete(task1)
      db.session.commit()

      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertNotIn("task_overdue", user_notifs)

  def _create_test_cases(self):
    """Create configuration to use for generating a new workflow."""
    def person_dict(person_id):
      return {
          "href": "/api/people/" + str(person_id),
          "id": person_id,
          "type": "Person"
      }
    role_id = models.all_models.AccessControlRole.query.filter(
        models.all_models.AccessControlRole.name == "Task Assignees",
        models.all_models.AccessControlRole.object_type == "TaskGroupTask",
    ).one().id
    self.one_time_workflow = {
        "title": "one time test workflow",
        "notify_on_change": True,
        "description": "some test workflow",
        # admin will be current user with id == 1
        "task_groups": [{
            "title": "one time task group",
            "contact": person_dict(self.user.id),
            "task_group_tasks": [{
                "title": "task 1",
                "description": "some task",
                "start_date": date(2017, 5, 5),  # Friday
                "end_date": date(2017, 5, 15),
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, self.user.id)],
            }, {
                "title": "task 2",
                "description": "some task 2",
                "start_date": date(2017, 5, 5),  # Friday
                "end_date": date(2017, 5, 16),
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, self.user.id)],
            }],
        }]
    }


@unittest.skip("unskip when import/export fixed for workflows")
class TestTaskOverdueNotificationsUsingImports(TestTaskOverdueNotifications):
  """Tests for overdue notifications when changing Tasks via imports."""

  # pylint: disable=invalid-name

  CSV_DIR = join(abspath(dirname(__file__)), "../converters/test_csvs/")

  def setUp(self):
    self.wf_generator = WorkflowsGenerator()
    self._fix_notification_init()

  @patch("ggrc.notifications.common.send_email")
  def test_creating_overdue_notifications_for_new_tasks(self, _):
    """Overdue notifications should be created for tasks created with imports.
    """
    Workflow.query.delete()
    models.Notification.query.delete()
    db.session.commit()

    filename = join(self.CSV_DIR, "workflow_small_sheet.csv")
    self.import_file(filename)

    workflow = Workflow.query.one()
    self.wf_generator.generate_cycle(workflow)
    response, workflow = self.wf_generator.activate_workflow(workflow)

    user = models.Person.query.filter(
        models.Person.email == 'user1@ggrc.com').one()

    with freeze_time("2020-01-01 00:00:00"):  # afer all tasks' due dates
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertIn("task_overdue", user_notifs)
      self.assertEqual(len(user_notifs["task_overdue"]), 4)

  @patch("ggrc.notifications.common.send_email")
  def test_overdue_notifications_when_task_due_date_is_changed(self, _):
    """Overdue notifications should adjust to task due date changes."""
    Workflow.query.delete()
    models.Notification.query.delete()
    db.session.commit()

    filename = join(self.CSV_DIR, "workflow_small_sheet.csv")
    self.import_file(filename)

    workflow = Workflow.query.one()
    self.wf_generator.generate_cycle(workflow)
    response, workflow = self.wf_generator.activate_workflow(workflow)

    user = models.Person.query.filter(
        models.Person.email == 'user1@ggrc.com').one()

    with freeze_time("2015-01-01 00:00:00"):  # before all tasks' due dates
      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertNotIn("task_overdue", user_notifs)

      # now modify task's due date and check if overdue notification appears
      task = CycleTaskGroupObjectTask.query.filter(
          CycleTaskGroupObjectTask.title == "task for wf-2").one()
      task_id, task_code = task.id, task.slug

      response = self.import_data(OrderedDict((
          ("object_type", "CycleTask"),
          ("Code*", task_code),
          ("Start Date", "12/15/2014"),
          ("Due Date", "12/31/2014"),
      )))
      self._check_csv_response(response, expected_messages={})

      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})
      self.assertIn("task_overdue", user_notifs)
      self.assertEqual(len(user_notifs["task_overdue"]), 1)
      self.assertIn(task_id, user_notifs["task_overdue"])
