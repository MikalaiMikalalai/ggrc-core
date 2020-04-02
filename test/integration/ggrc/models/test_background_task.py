# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Tests for background_task model."""

import ddt
import mock

from ggrc.app import app

from integration.ggrc import api_helper
from integration.ggrc import TestCase
from integration.ggrc.generator import ObjectGenerator
from integration.ggrc.models import factories


class TestBackgroundTask(TestCase):
  """Tests for background task model."""

  def setUp(self):
    """setUp, nothing else to add."""
    super(TestBackgroundTask, self).setUp()
    self.api = api_helper.Api()
    self.object_generator = ObjectGenerator()

  def test_bg_task_from_post(self):
    """Test filtering of GET response for BackgroundTask"""
    from ggrc.models import all_models

    with self.object_generator.api.as_external():
      response, _ = self.object_generator.generate_object(
          all_models.Control, with_background_tasks=True)
    self.assertEqual(response.status_code, 201)
    bg_tasks = all_models.BackgroundTask.query.filter(
        all_models.BackgroundTask.name.like("%POST%")).all()
    self.assertEqual(len(bg_tasks), 1)

    content = self.api.client.get("/api/background_tasks")
    self.assert200(content)
    bg_tasks_content = \
        content.json['background_tasks_collection']['background_tasks']
    self.assertEqual(set(bg_tasks_content[0].keys()),
                     {"id", "selfLink", "status", "type"})

    task_id = bg_tasks[0].id
    content = self.api.client.get("/api/background_tasks/{}".format(task_id))
    self.assert200(content)
    bg_task_content = \
        content.json['background_task']
    self.assertEqual(set(bg_task_content.keys()),
                     {"id", "selfLink", "status", "type"})

  def test_bg_error_task(self):
    """Test error BackgroundTask for success response."""
    from ggrc.views import create_missing_revisions

    with mock.patch(
        "ggrc.views.app.make_response",
        return_value=app.make_response(
            ("error", 500, [("Content-Type", "text/html")])
        )
    ):
      with mock.patch("ggrc.utils.revisions.do_missing_revisions"):
        bg_task = factories.BackgroundTaskFactory(name="test_error_task_queue")
        response = create_missing_revisions(bg_task)
        self.assertEqual(response.status_code, 200)

  def test_bg_success_task(self):
    """Test success BackgroundTask for success response."""
    from ggrc.views import create_missing_revisions

    with mock.patch("ggrc.utils.revisions.do_missing_revisions"):
      bg_task = factories.BackgroundTaskFactory(name="test_success_task_queue")
      response = create_missing_revisions(bg_task)
      self.assertEqual(response.status_code, 200)


class TestPermissions(TestCase):
  """Test permissions for background tasks"""

  def setUp(self):
    super(TestPermissions, self).setUp()
    self.api = api_helper.Api()
    self.object_generator = ObjectGenerator()
    self.init_users()

  def init_users(self):
    """ Init users needed by the test cases """
    users = [("reader", "Reader"),
             ("admin", "Administrator"),
             ("creator", "Creator")]
    self.users = {}
    for (name, role) in users:
      _, user = self.object_generator.generate_person(
          data={"name": name}, user_role=role)
      self.users[name] = user

  def test_bg_tasks_access(self):
    """Only admin can use admin requirement"""
    from ggrc.models import all_models

    with self.object_generator.api.as_external():
      response, _ = self.object_generator.generate_object(
          all_models.Control, with_background_tasks=True)
    self.assertEqual(response.status_code, 201)

    for role in ("reader", "creator", "admin"):
      self.api.set_user(self.users[role])
      content = self.api.client.get("/api/background_tasks")
      self.assert200(content)
      bg_tasks_content = \
          content.json['background_tasks_collection']['background_tasks']
      for bg_task_content in bg_tasks_content:
        self.assertEqual(set(bg_task_content.keys()),
                         {"id", "selfLink", "status", "type"})
      self.assertTrue(len(bg_tasks_content) >= 1)


@ddt.ddt
class TestCronJobs(TestCase):
  """Test CRON jobs protection"""
  # pylint: disable=unused-argument
  def setUp(self):
    super(TestCronJobs, self).setUp()
    self.api = api_helper.Api()

  @ddt.data(({'X-Appengine-Cron': True}, 200), ({}, 403))
  @ddt.unpack
  @mock.patch("ggrc.notifications.common.send_email")
  def test_cron_jobs_protection(self, headers, status_code, send_email):
    """Test CRON jobs CRON jobs protected with 'X-Appengine-Cron' header"""
    response = self.api.client.get("nightly_cron_endpoint", headers=headers)
    self.assertEqual(response.status_code, status_code)
