# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Tests for /api/people endpoints."""

import json
from datetime import date

import ddt
from freezegun import freeze_time

from ggrc.models import all_models
from ggrc.utils import create_stub

from integration.ggrc import generator
from integration.ggrc.access_control import acl_helper
from integration.ggrc.models import factories
from integration.ggrc.services import TestCase
from integration.ggrc.query_helper import WithQueryApi
from integration.ggrc_workflows.generator import WorkflowsGenerator
from integration.ggrc.api_helper import Api
from integration.ggrc_basic_permissions.models \
    import factories as rbac_factories


@ddt.ddt
class TestPersonResource(TestCase, WithQueryApi):
  """Tests for special people api endpoints."""

  def setUp(self):
    super(TestPersonResource, self).setUp()
    self.client.get("/login")
    self.api = Api()
    self.generator = WorkflowsGenerator()

  @staticmethod
  def _create_users_names_rbac(users):
    """Create name and Creator role for users, created vid PersonFactory"""
    if not users:
      return
    roles = {r.name: r for r in all_models.Role.query.all()}
    for user in users:
      user.name = user.email.split("@")[0]
      rbac_factories.UserRoleFactory(role=roles["Creator"], person=user)

  def test_task_count_empty(self):
    """Test query count without any workflows and tasks."""
    user = all_models.Person.query.first()
    response = self.client.get("/api/people/{}/task_count".format(user.id))
    self.assertEqual(
        response.json,
        {"open_task_count": 0, "has_overdue": False}
    )

  @ddt.data(
      (True, [
          ("task 1", "Finished", 3, True, 3),
          ("task 1", "Verified", 2, True, 3),
          ("task 2", "Declined", 2, True, 3),
          ("task 2", "Verified", 1, False, 3),
          ("task 2", "Finished", 2, True, 3),
          ("task 3", "Verified", 1, True, 3),
          ("task 2", "Verified", 0, False, 3),
      ]),
      (False, [
          ("task 1", "Finished", 2, True, 3),
          ("task 2", "In Progress", 2, True, 3),
          ("task 2", "Finished", 1, False, 3),
          ("task 3", "Finished", 0, False, 3),
      ]),
  )
  @ddt.unpack
  def test_task_count(self, is_verification_needed, transitions):
    """Test person task counts.

    This tests checks for correct task counts
     - with inactive workflows and
     - with overdue tasks
     - without overdue tasks
     - with finished overdue tasks

    The four checks are done in a single test due to complex differences
    between tests that make ddt cumbersome and the single test also improves
    integration test performance due to slow workflow setup stage.
    """
    # pylint: disable=too-many-locals

    user = all_models.Person.query.first()
    dummy_user = factories.PersonFactory()
    user_id = user.id
    role_id = all_models.AccessControlRole.query.filter(
        all_models.AccessControlRole.name == "Task Assignees",
        all_models.AccessControlRole.object_type == "TaskGroupTask",
    ).one().id
    secondary_role_id = all_models.AccessControlRole.query.filter(
        all_models.AccessControlRole.name == "Task Secondary Assignees",
        all_models.AccessControlRole.object_type == "TaskGroupTask",
    ).one().id

    one_time_workflow = {
        "title": "Person resource test workflow",
        "notify_on_change": True,
        "description": "some test workflow",
        "owners": [create_stub(user)],
        "is_verification_needed": is_verification_needed,
        "task_groups": [{
            "title": "one time task group",
            "contact": create_stub(user),
            "task_group_tasks": [{
                "title": "task 1",
                "description": "some task",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, user.id),
                    acl_helper.get_acl_json(secondary_role_id, user.id)
                ],
                "start_date": date(2017, 5, 5),
                "end_date": date(2017, 8, 15),
            }, {
                "title": "task 2",
                "description": "some task 3",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, user.id),
                    acl_helper.get_acl_json(secondary_role_id, user.id),
                    acl_helper.get_acl_json(secondary_role_id, dummy_user.id)
                ],
                "start_date": date(2017, 5, 5),
                "end_date": date(2017, 9, 16),
            }, {
                "title": "task 3",
                "description": "some task 4",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, user.id),
                    acl_helper.get_acl_json(role_id, dummy_user.id)
                ],
                "start_date": date(2017, 6, 5),
                "end_date": date(2017, 10, 16),
            }, {
                "title": "dummy task 4",  # task should not counted
                "description": "some task 4",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, dummy_user.id)],
                "start_date": date(2017, 6, 5),
                "end_date": date(2017, 11, 17),
            }, {
                "title": "dummy task 5",  # task should not counted
                "description": "some task 4",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, dummy_user.id)],
                "start_date": date(2017, 6, 5),
                "end_date": date(2017, 11, 18),
            }],
            "task_group_objects": []
        }]
    }

    inactive_workflow = {
        "title": "Activated workflow with archived cycles",
        "notify_on_change": True,
        "description": "Extra test workflow",
        "owners": [create_stub(user)],
        "task_groups": [{
            "title": "Extra task group",
            "contact": create_stub(user),
            "task_group_tasks": [{
                "title": "not counted existing task",
                "description": "",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, user.id)],
                "start_date": date(2017, 5, 5),
                "end_date": date(2017, 8, 15),
            }],
            "task_group_objects": []
        }]
    }

    with freeze_time("2017-10-16 05:09:10"):
      self.client.get("/login")
      # Activate normal one time workflow
      _, workflow = self.generator.generate_workflow(one_time_workflow)
      _, cycle = self.generator.generate_cycle(workflow)
      tasks = {t.title: t for t in cycle.cycle_task_group_object_tasks}
      _, workflow = self.generator.activate_workflow(workflow)

      # Activate and close the inactive workflow
      _, workflow = self.generator.generate_workflow(inactive_workflow)
      _, cycle = self.generator.generate_cycle(workflow)
      _, workflow = self.generator.activate_workflow(workflow)
      self.generator.modify_object(cycle, data={"is_current": False})

    with freeze_time("2017-7-16 07:09:10"):
      self.client.get("/login")
      response = self.client.get("/api/people/{}/task_count".format(user_id))
      self.assertEqual(
          response.json,
          {"open_task_count": 3, "has_overdue": False}
      )

    with freeze_time("2017-10-16 08:09:10"):  # same day as task 3 end date
      self.client.get("/login")
      response = self.client.get("/api/people/{}/task_count".format(user_id))
      self.assertEqual(
          response.json,
          {"open_task_count": 3, "has_overdue": True}
      )

      for task, status, count, overdue, my_work_count in transitions:
        self.generator.modify_object(tasks[task], data={"status": status})
        task_count_response = \
            self.client.get("/api/people/{}/task_count".format(user_id))
        my_work_count_response = \
            self.client.get("/api/people/{}/my_work_count".format(user_id))

        self.assertEqual(
            task_count_response.json,
            {"open_task_count": count, "has_overdue": overdue}
        )

        self.assertEqual(
            my_work_count_response.json["CycleTaskGroupObjectTask"],
            my_work_count
        )

  def test_task_count_multiple_wfs(self):
    """Test task count with both verified and non verified workflows.

    This checks task counts with 4 tasks
        2017, 8, 15  - verification needed
        2017, 11, 18  - verification needed
        2017, 8, 15  - No verification needed
        2017, 11, 18  - No verification needed
    """

    user = all_models.Person.query.first()
    user_id = user.id
    role_id = all_models.AccessControlRole.query.filter(
        all_models.AccessControlRole.name == "Task Assignees",
        all_models.AccessControlRole.object_type == "TaskGroupTask",
    ).one().id
    workflow_template = {
        "title": "verified workflow",
        "owners": [create_stub(user)],
        "is_verification_needed": True,
        "task_groups": [{
            "title": "one time task group",
            "contact": create_stub(user),
            "task_group_tasks": [{
                "title": "task 1",
                "description": "some task",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, user.id)],
                "start_date": date(2017, 5, 5),
                "end_date": date(2017, 8, 15),
            }, {
                "title": "dummy task 5",
                "description": "some task 4",
                "access_control_list": [
                    acl_helper.get_acl_json(role_id, user.id)],
                "start_date": date(2017, 6, 5),
                "end_date": date(2017, 11, 18),
            }],
            "task_group_objects": []
        }]
    }

    with freeze_time("2017-10-16 05:09:10"):
      self.client.get("/login")
      verified_workflow = workflow_template.copy()
      verified_workflow["is_verification_needed"] = True
      _, workflow = self.generator.generate_workflow(verified_workflow)
      _, cycle = self.generator.generate_cycle(workflow)
      verified_tasks = {
          task.title: task
          for task in cycle.cycle_task_group_object_tasks
      }
      _, workflow = self.generator.activate_workflow(workflow)

      non_verified_workflow = workflow_template.copy()
      non_verified_workflow["is_verification_needed"] = False
      _, workflow = self.generator.generate_workflow(non_verified_workflow)
      _, cycle = self.generator.generate_cycle(workflow)
      non_verified_tasks = {
          task.title: task
          for task in cycle.cycle_task_group_object_tasks
      }
      _, workflow = self.generator.activate_workflow(workflow)

    with freeze_time("2017-7-16 07:09:10"):
      self.client.get("/login")
      response = self.client.get("/api/people/{}/task_count".format(user_id))
      self.assertEqual(
          response.json,
          {"open_task_count": 4, "has_overdue": False}
      )

    with freeze_time("2017-10-16 08:09:10"):
      self.client.get("/login")
      response = self.client.get("/api/people/{}/task_count".format(user_id))
      self.assertEqual(
          response.json,
          {"open_task_count": 4, "has_overdue": True}
      )

      # transition 1, task that needs verification goes to finished state. This
      # transition should not change anything
      self.generator.modify_object(
          verified_tasks["task 1"],
          data={"status": "Finished"}
      )
      response = self.client.get("/api/people/{}/task_count".format(user_id))
      self.assertEqual(
          response.json,
          {"open_task_count": 4, "has_overdue": True}
      )

      # transition 2, task that needs verification goes to verified state. This
      # transition should reduce task count.
      self.generator.modify_object(
          verified_tasks["task 1"],
          data={"status": "Verified"}
      )
      response = self.client.get("/api/people/{}/task_count".format(user_id))
      self.assertEqual(
          response.json,
          {"open_task_count": 3, "has_overdue": True}
      )

      # transition 3, task that does not need verification goes into Finished
      # state. This transition should reduce task count and remove all overdue
      # tasks
      self.generator.modify_object(
          non_verified_tasks["task 1"],
          data={"status": "Finished"}
      )
      response = self.client.get("/api/people/{}/task_count".format(user_id))
      self.assertEqual(
          response.json,
          {"open_task_count": 2, "has_overdue": False}
      )

  @ddt.data(("Creator", 403),
            ("Reader", 403),
            ("Editor", 200),
            ("Administrator", 200))
  @ddt.unpack
  def test_person_editing(self, role_name, status):
    """{0} should receive {1} status code on edit Person."""
    role = all_models.Role.query.filter(
        all_models.Role.name == role_name
    ).one()
    with factories.single_commit():
      client_user = factories.PersonFactory()
      rbac_factories.UserRoleFactory(role=role, person=client_user)
    self.api.set_user(client_user)
    self.client.get("/login")
    base_email = "test@example.com"
    person = factories.PersonFactory(email=base_email)
    person_id = person.id
    new_email = "new_{}".format(base_email)
    resp = self.api.put(person, {"email": new_email})
    self.assertEqual(status, resp.status_code)
    person = all_models.Person.query.get(person_id)
    if status == 200:
      self.assertEqual(new_email, person.email)
    else:
      self.assertEqual(base_email, person.email)


@ddt.ddt
class TestPersonResourcePopulated(TestCase, WithQueryApi):
  """Tests meant to be run on a populated database."""

  MY_WORK_OBJECTS = [
      # "Person",  this also exists but should be removed since it's not used.
      "Issue",
      "AccessGroup",
      "Assessment",
      "Audit",
      "Contract",
      "Control",
      "DataAsset",
      "Document",
      "Facility",
      "Evidence",
      "Market",
      "Objective",
      "OrgGroup",
      "Policy",
      "Process",
      "Product",
      "Program",
      "Project",
      "Regulation",
      "Risk",
      "Requirement",
      "Standard",
      "System",
      "Threat",
      "Vendor",
      "CycleTaskGroupObjectTask",
      "Metric",
      "TechnologyEnvironment",
      "ProductGroup",
      "KeyReport",
      "AccountBalance",
  ]

  ALL_OBJECT_COUNTS = [
      "Issue",
      "AccessGroup",
      "Assessment",
      "Audit",
      "Contract",
      "Control",
      "DataAsset",
      "Document",
      "Facility",
      "Evidence",
      "Market",
      "Objective",
      "OrgGroup",
      "Policy",
      "Process",
      "Product",
      "Program",
      "Project",
      "Regulation",
      "Risk",
      "Requirement",
      "Standard",
      "System",
      "Threat",
      "Vendor",
      "CycleTaskGroupObjectTask",
      "Workflow",
      "Metric",
      "TechnologyEnvironment",
      "ProductGroup",
      "KeyReport",
      "AccountBalance",
  ]

  def setUp(self):
    super(TestPersonResourcePopulated, self).setUp()
    self.client.get("/login")
    self.api = Api()
    self.objgen = generator.ObjectGenerator()

  def get_counts_query(self, user_id):
    """Returns counts query for all objects in MY_WORK_OBJECTS."""
    return [
        {
            "object_name": object_name,
            "type": "count",
            "filters": {
                "expression": {
                    "object_name": "Person",
                    "op": {"name": "owned"},
                    "ids": [user_id]
                },
                "keys": [],
                "order_by": {"keys": [], "order": "", "compare": None}
            },
        }
        for object_name in self.MY_WORK_OBJECTS
    ]

  @ddt.data(*[
      (user.id, user.email, user.name)
      for user in all_models.Person.query
  ])
  @ddt.unpack
  def test_my_work_counts(self, user_id, user_email, user_name):
    """Compare my work counts with query API response.

    This test is meant to be run manually on a fully populated database.
    """

    user_headers = {
        "X-ggrc-user": json.dumps({"name": user_name, "email": user_email})
    }
    self.client.get("/login", headers=user_headers)

    query = self.get_counts_query(user_id)
    url = "/api/people/{}/my_work_count".format(user_id)
    response = self._post(query)
    counts = {
        item.values()[0]["object_name"]: item.values()[0]["count"]
        for item in response.json
    }

    response = self.client.get(url)
    if response.status_code == 403:
      # We skip inactive users that don't have access to view their counts
      return

    my_work_count = response.json

    self.assertEqual(
        (user_id, user_email, counts),
        (user_id, user_email, my_work_count),
    )

  @ddt.data("Creator", "Reader", "Editor", "Administrator")
  def test_my_work_counts_for_audits(self, role):
    """Test compares my work counts with query API response for Audits.

    For current user should return Audits where user is owner and
    Audits that have user-owned Assessments.
    Actual test - create 2 audits with different persons as Audit Captains,
    For second audit create asmnt with user1 as creator.
    Should return both audits for user1 as owner."""
    # pylint: disable=too-many-locals

    _, person = self.objgen.generate_person(user_role=role)
    person_name, person_id, person_email =\
        person.name, person.id, person.email
    _, another_person = self.objgen.generate_person(user_role="Administrator")
    another_person_id = another_person.id

    audit_captain_role = all_models.AccessControlRole.query.filter_by(
        name="Audit Captains",
        object_type="Audit"
    ).one()
    audit_captain_role_id = audit_captain_role.id
    creator_role = all_models.AccessControlRole.query.filter_by(
        name="Creators",
        object_type="Assessment"
    ).one()
    creator_role_id = creator_role.id

    program = factories.ProgramFactory()

    audit1 = self.api.post(all_models.Audit, {
        "audit": {
            "title": "audit1",
            'program': {'id': program.id, "type": "Program"},
            "access_control_list": [{
                "ac_role_id": audit_captain_role_id,
                "person": {
                    "id": person_id,
                    "type": "Person"
                }
            }]
        }
    })
    self.assert201(audit1)

    audit2 = self.api.post(all_models.Audit, {
        "audit": {
            "title": "audit2",
            'program': {'id': program.id, "type": "Program"},
            "access_control_list": [{
                "ac_role_id": audit_captain_role_id,
                "person": {
                    "id": another_person_id,
                    "type": "Person"
                }
            }]
        }
    })
    self.assert201(audit2)
    audit2_id = audit2.json.get("audit").get("id")

    assessment = self.api.post(
        all_models.Assessment,
        {
            "assessment": {
                "title": "Assessment2",
                "audit": {"id": audit2_id, "type": "Audit"},
                "access_control_list": [{
                    "ac_role_id": creator_role_id,
                    "person": {
                        "id": person_id,
                        "type": "Person"
                    },
                }],
            },
        }
    )
    self.assert201(assessment)

    self.client.get(
        "/login",
        headers={
            "X-ggrc-user": json.dumps({"name": person_name,
                                       "email": person_email})
        },
    )

    response = self._post(self.get_counts_query(person_id))
    counts = {
        item.values()[0]["object_name"]: item.values()[0]["count"]
        for item in response.json
    }

    url = "/api/people/{}/my_work_count".format(person_id)
    my_work_counts = self.client.get(url).json

    self.assertEqual(counts, my_work_counts)

  @ddt.data(*[
      (user.id, user.email, user.name)
      for user in all_models.Person.query
  ])
  @ddt.unpack
  def test_all_object_counts(self, user_id, user_email, user_name):
    """Compare my work counts with query API response.

    This test is meant to be run manually on a fully populated database.
    """
    def get_query():
      return [
          {
              "object_name": object_name,
              "filters": {
                  "expression": {},
                  "keys": [],
                  "order_by": {"keys": [], "order": "", "compare": None}
              },
              "type": "count"
          }
          for object_name in self.ALL_OBJECT_COUNTS
      ]

    user_headers = {
        "X-ggrc-user": json.dumps({"name": user_name, "email": user_email})
    }
    self.client.get("/login", headers=user_headers)

    query = get_query()
    url = "/api/people/{}/all_objects_count".format(user_id)
    response = self._post(query)
    counts = {
        item.values()[0]["object_name"]: item.values()[0]["count"]
        for item in response.json
    }

    response = self.client.get(url)
    if response.status_code == 403:
      # We skip inactive users that don't have access to view their counts
      return

    my_work_count = response.json

    self.assertEqual(
        (user_id, user_email, counts),
        (user_id, user_email, my_work_count),
    )
