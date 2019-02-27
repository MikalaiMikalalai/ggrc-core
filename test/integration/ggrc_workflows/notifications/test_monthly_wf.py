# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
import datetime as dt
from freezegun import freeze_time
from mock import patch

from ggrc.notifications import common
from ggrc.models import Notification, Person
from ggrc_workflows import start_recurring_cycles
from integration.ggrc import TestCase
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
    _, self.person_1 = self.object_generator.generate_person(
        user_role="Administrator")
    _, self.person_2 = self.object_generator.generate_person(
        user_role="Administrator")
    self.create_test_cases()

    def init_decorator(init):
      def new_init(self, *args, **kwargs):
        init(self, *args, **kwargs)
        if hasattr(self, "created_at"):
          self.created_at = dt.datetime.now()
      return new_init

    Notification.__init__ = init_decorator(Notification.__init__)

  @patch("ggrc.notifications.common.send_email")
  def test_auto_generate_cycle(self, mock_mail):

    person_1_email = Person.query.get(self.person_1.id).email
    with freeze_time("2015-04-01"):
      _, wf = self.wf_generator.generate_workflow(self.monthly_workflow_1)
      self.wf_generator.activate_workflow(wf)
      _, notif_data = common.get_daily_notifications()
      self.assertNotIn(person_1_email, notif_data)

    with freeze_time("2015-04-02"):
      self.api.client.get("nightly_cron_endpoint")
      _, notif_data = common.get_daily_notifications()
      self.assertNotIn(person_1_email, notif_data)
      start_recurring_cycles()
      _, notif_data = common.get_daily_notifications()
      self.assertNotIn(person_1_email, notif_data)

    # cycle starts on monday - 6th, and not on 5th
    with freeze_time("2015-04-03"):
      start_recurring_cycles()
      _, notif_data = common.get_daily_notifications()
      self.assertIn(person_1_email, notif_data)
      self.assertIn("cycle_started", notif_data[person_1_email])

    with freeze_time("2015-04-15"):  # one day befor due date
      _, notif_data = common.get_daily_notifications()
      self.assertIn(person_1_email, notif_data)

    with freeze_time("2015-04-25"):  # due date
      _, notif_data = common.get_daily_notifications()
      self.assertIn(person_1_email, notif_data)

  @patch("ggrc.notifications.common.send_email")
  def test_manual_generate_cycle(self, mock_mail):

    with freeze_time("2015-04-01"):
      _, wf = self.wf_generator.generate_workflow(self.monthly_workflow_1)
      self.wf_generator.activate_workflow(wf)

      person_1 = Person.query.get(self.person_1.id)

    with freeze_time("2015-04-03"):
      _, notif_data = common.get_daily_notifications()

    with freeze_time("2015-04-03"):
      _, cycle = self.wf_generator.generate_cycle(wf)
      _, notif_data = common.get_daily_notifications()
      person_1 = Person.query.get(self.person_1.id)
      self.assertIn("cycle_started", notif_data[person_1.email])

    with freeze_time("2015-05-03"):  # two days befor due date
      _, notif_data = common.get_daily_notifications()
      person_1 = Person.query.get(self.person_1.id)
      self.assertIn(person_1.email, notif_data)

  def create_test_cases(self):
    def person_dict(person_id):
      return {
          "href": "/api/people/%d" % person_id,
          "id": person_id,
          "type": "Person"
      }

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
                "contact": person_dict(self.person_1.id),
                "start_date": dt.date(2015, 4, 5),
                "end_date": dt.date(2015, 4, 25),
            }, {
                "title": "task 2",
                "description": "some task",
                "contact": person_dict(self.person_1.id),
                "start_date": dt.date(2015, 4, 10),
                "end_date": dt.date(2015, 4, 21),
            }],
        }, {
            "title": "another one time task group",
            "contact": person_dict(self.person_1.id),
            "task_group_tasks": [{
                "title": "task 1 in tg 2",
                "description": "some task",
                "contact": person_dict(self.person_1.id),
                "start_date": dt.date(2015, 4, 15),
                "end_date": dt.date(2015, 4, 15),
            }, {
                "title": "task 2 in tg 2",
                "description": "some task",
                "contact": person_dict(self.person_2.id),
                "start_date": dt.date(2015, 4, 15),
                "end_date": dt.date(2015, 4, 28),
            }],
        }]
    }
