# -*- coding: utf-8 -*-

# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Integration tests for sending the notifications about WF tasks "due soon".
"""

import functools
from datetime import date, datetime, timedelta
import sqlalchemy as sa

from freezegun import freeze_time
from mock import patch

import ddt

from ggrc import models
from ggrc.notifications import common

from integration.ggrc import TestCase
from integration.ggrc_workflows.generator import WorkflowsGenerator
from integration.ggrc.access_control import acl_helper
from integration.ggrc.api_helper import Api
from integration.ggrc.generator import ObjectGenerator


@ddt.ddt
class TestTaskDueNotifications(TestCase):
  """Test suite for task due soon/today notifications."""

  # pylint: disable=invalid-name

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

  def setUp(self):
    super(TestTaskDueNotifications, self).setUp()
    self.api = Api()
    self.wf_generator = WorkflowsGenerator()
    self.object_generator = ObjectGenerator()
    models.Notification.query.delete()

    self._fix_notification_init()

    self.random_objects = self.object_generator.generate_random_objects(2)
    _, self.user = self.object_generator.generate_person(
        user_role="Administrator")

    role_id = models.all_models.AccessControlRole.query.filter(
        models.all_models.AccessControlRole.name == "Task Assignees",
        models.all_models.AccessControlRole.object_type == "TaskGroupTask",
    ).one().id

    self.one_time_workflow = {
        "title": "one time test workflow",
        "notify_on_change": True,
        "description": "some test workflow",
        "is_verification_needed": False,
        # admin will be current user with id == 1
        "task_groups": [{
            "title": "one time task group",
            "contact": {
                "href": "/api/people/{}".format(self.user.id),
                "id": self.user.id,
                "type": "Person",
            },
            "task_group_tasks": [{
                "title": "task 1",
                "description": "some task",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, self.user.id)],
                "start_date": date(2017, 5, 15),
                "end_date": date(2017, 6, 11),
            }, {
                "title": "task 2",
                "description": "some task 2",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, self.user.id)],
                "start_date": date(2017, 5, 8),
                "end_date": date(2017, 6, 12),
            }, {
                "title": "task 3",
                "description": "some task 3",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, self.user.id)],
                "start_date": date(2017, 5, 31),
                "end_date": date(2017, 6, 13),
            }, {
                "title": "task 4",
                "description": "some task 4",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, self.user.id)],
                "start_date": date(2017, 6, 2),
                "end_date": date(2017, 6, 14),
            }, {
                "title": "task 5",
                "description": "some task 5",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, self.user.id)],
                "start_date": date(2017, 6, 8),
                "end_date": date(2017, 6, 15),
            }],
        }]
    }

  @ddt.unpack
  @ddt.data(
      ("2017-06-12 12:12:12", ["task 1"], ["task 2"], ["task 3"]),
      ("2017-06-13 13:13:13", ["task 1", "task 2"], ["task 3"], ["task 4"]),
  )
  @patch("ggrc.notifications.common.send_email")
  def test_creating_obsolete_notifications(
      self, fake_now, expected_overdue, expected_due_today, expected_due_in, _
  ):
    """Notifications already obsolete on creation date should not be created.
    """
    with freeze_time("2017-06-12 09:39:32"):
      tmp = self.one_time_workflow.copy()
      _, workflow = self.wf_generator.generate_workflow(tmp)
      self.wf_generator.generate_cycle(workflow)
      response, workflow = self.wf_generator.activate_workflow(workflow)
      self.assert200(response)

    user = models.Person.query.get(self.user.id)

    with freeze_time(fake_now):
      # mark all yeasterday notifications as sent
      models.all_models.Notification.query.filter(
          sa.func.DATE(models.all_models.Notification.send_on) < date.today()
      ).update({models.all_models.Notification.sent_at:
                datetime.now() - timedelta(1)},
               synchronize_session="fetch")

      _, notif_data = common.get_daily_notifications()
      user_notifs = notif_data.get(user.email, {})

      actual_overdue = [n['title'] for n in
                        user_notifs.get("task_overdue", {}).itervalues()]
      actual_overdue.sort()
      self.assertEqual(actual_overdue, expected_overdue)

      self.assertEqual(
          [n['title'] for n in user_notifs.get("due_today", {}).itervalues()],
          expected_due_today)

      self.assertEqual(
          [n['title'] for n in user_notifs.get("due_in", {}).itervalues()],
          expected_due_in)
