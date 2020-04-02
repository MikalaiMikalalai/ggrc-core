# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
import datetime as dt
from freezegun import freeze_time
from mock import patch

from ggrc.notifications import common
from ggrc.models import all_models
from ggrc_workflows import start_recurring_cycles
from integration.ggrc import TestCase
from integration.ggrc.access_control import acl_helper
from integration.ggrc_workflows.generator import WorkflowsGenerator
from integration.ggrc.api_helper import Api
from integration.ggrc.generator import ObjectGenerator


class TestMonthlyWorkflowNotification(TestCase):

  """ This class contains simple one time workflow tests that are not
  in the gsheet test grid
  """

  def setUp(self):
    super(TestMonthlyWorkflowNotification, self).setUp()
    self.api = Api()
    self.wf_generator = WorkflowsGenerator()
    self.object_generator = ObjectGenerator()

    self.random_objects = self.object_generator.generate_random_objects()
    self.person_1 = self.create_user_with_role(role="Administrator")
    self.person_2 = self.create_user_with_role(role="Administrator")
    self.secondary_assignee = self.create_user_with_role(role="Reader")
    self.create_test_cases()

    def init_decorator(init):
      def new_init(self, *args, **kwargs):
        init(self, *args, **kwargs)
        if hasattr(self, "created_at"):
          self.created_at = dt.datetime.now()
      return new_init

    all_models.Notification.__init__ = init_decorator(
        all_models.Notification.__init__)

  @patch("ggrc.notifications.common.send_email")
  def test_auto_generate_cycle(self, mock_mail):
    """Test auto recurring cycles"""

    with freeze_time("2015-04-01"):
      _, wf = self.wf_generator.generate_workflow(self.monthly_workflow_1)
      self.wf_generator.activate_workflow(wf)
      _, notif_data = common.get_daily_notifications()
      contact = self.person_1
      task_assignees = [contact, self.secondary_assignee]

      for user in task_assignees:
        self.assertNotIn(user.email, notif_data)

    with freeze_time("2015-04-02"):
      headers = {
          'X-Appengine-Cron': True,
      }
      response = self.api.client.get("nightly_cron_endpoint", headers=headers)
      self.assert200(response)
      _, notif_data = common.get_daily_notifications()
      for user in task_assignees:
        self.assertNotIn(user.email, notif_data)
      start_recurring_cycles()
      _, notif_data = common.get_daily_notifications()
      for user in task_assignees:
        self.assertNotIn(user.email, notif_data)

    # cycle starts on monday - 6th, and not on 5th
    with freeze_time("2015-04-03"):
      from ggrc.login import noop
      noop.login()
      start_recurring_cycles()
      _, notif_data = common.get_daily_notifications()
      for user in task_assignees:
        self.assertIn(user.email, notif_data)

      # cycle started notifs available only for contact
      self.assertIn("cycle_started", notif_data[contact.email])

    with freeze_time("2015-04-15"):  # one day before due date
      _, notif_data = common.get_daily_notifications()
      for user in task_assignees:
        self.assertIn(user.email, notif_data)

    with freeze_time("2015-04-25"):  # due date
      _, notif_data = common.get_daily_notifications()
      for user in task_assignees:
        self.assertIn(user.email, notif_data)

  @patch("ggrc.notifications.common.send_email")
  def test_manual_generate_cycle(self, mock_mail):
    """Test generation of manual cycles"""

    with freeze_time("2015-04-01"):
      _, wf = self.wf_generator.generate_workflow(self.monthly_workflow_1)
      self.wf_generator.activate_workflow(wf)

    with freeze_time("2015-04-03"):
      _, cycle = self.wf_generator.generate_cycle(wf)
      contact = self.person_1
      task_assignees = [contact, self.secondary_assignee]
      _, notif_data = common.get_daily_notifications()

      # cycle started notifs available only for contact
      self.assertIn("cycle_started", notif_data[contact.email])

    with freeze_time("2015-05-03"):  # two days before due date
      _, notif_data = common.get_daily_notifications()
      for user in task_assignees:
        self.assertIn(user.email, notif_data)

  def create_test_cases(self):
    def person_dict(person_id):
      return {
          "href": "/api/people/%d" % person_id,
          "id": person_id,
          "type": "Person"
      }

    task_secondary_assignee = all_models.AccessControlRole.query.filter(
        all_models.AccessControlRole.name == "Task Secondary Assignees",
        all_models.AccessControlRole.object_type == "TaskGroupTask",
    ).one().id

    self.monthly_workflow_1 = {
        "title": "test monthly wf notifications",
        "notify_on_change": True,
        "description": "some test workflow",
        # admin will be current user with id == 1
        "unit": "month",
        "recurrences": True,
        "repeat_every": 1,
        "task_groups": [{
            "title": "one time task group",
            "contact": person_dict(self.person_1.id),
            "task_group_tasks": [{
                "title": "task 1",
                "description": "some task",
                "access_control_list": [
                    acl_helper.get_acl_json(task_secondary_assignee,
                                            self.secondary_assignee.id),
                ],
                "contact": person_dict(self.person_1.id),
                "start_date": dt.date(2015, 4, 5),
                "end_date": dt.date(2015, 4, 25),
            }, {
                "title": "task 2",
                "description": "some task",
                "access_control_list": [
                    acl_helper.get_acl_json(task_secondary_assignee,
                                            self.secondary_assignee.id),
                ],
                "contact": person_dict(self.person_1.id),
                "start_date": dt.date(2015, 4, 10),
                "end_date": dt.date(2015, 4, 21),
            }],
            "task_group_objects": self.random_objects[:2]
        }, {
            "title": "another one time task group",
            "contact": person_dict(self.person_1.id),
            "task_group_tasks": [{
                "title": "task 1 in tg 2",
                "description": "some task",
                "access_control_list": [
                    acl_helper.get_acl_json(task_secondary_assignee,
                                            self.secondary_assignee.id),
                ],
                "contact": person_dict(self.person_1.id),
                "start_date": dt.date(2015, 4, 15),
                "end_date": dt.date(2015, 4, 15),
            }, {
                "title": "task 2 in tg 2",
                "description": "some task",
                "access_control_list": [
                    acl_helper.get_acl_json(task_secondary_assignee,
                                            self.secondary_assignee.id),
                ],
                "contact": person_dict(self.person_2.id),
                "start_date": dt.date(2015, 4, 15),
                "end_date": dt.date(2015, 4, 28),
            }],
            "task_group_objects": []
        }]
    }
