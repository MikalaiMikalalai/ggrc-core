# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Integration test for TestWithReadOnlyAccess mixin"""

# pylint: disable=invalid-name,too-many-arguments,too-many-lines

from collections import OrderedDict
import json

import ddt

from ggrc import views
from ggrc.converters import errors
from ggrc.models import get_model, all_models, mixins
from integration.ggrc import TestCase
from integration.ggrc import api_helper
from integration.ggrc.generator import ObjectGenerator
from integration.ggrc import factories
from integration.ggrc import query_helper
from integration.ggrc_basic_permissions.models \
    import factories as rbac_factories


_NOT_SPECIFIED = '<NOT_SPECIFIED>'


@ddt.ddt
class TestWithReadOnlyAccessAPI(TestCase, query_helper.WithQueryApi):
  """Test WithReadOnlyAccess mixin"""

  def setUp(self):
    super(TestWithReadOnlyAccessAPI, self).setUp()
    self.object_generator = ObjectGenerator()
    self.object_generator.api.login_as_normal()

  @ddt.data(
      ('System', True),
      ('System', False),
      ('System', None),
      ('System', _NOT_SPECIFIED),
      ('System', "qwert"),
  )
  @ddt.unpack
  def test_readonly_ignored_on_post(self, obj_type, readonly):
    """Test flag readonly ignored on object {0} POST for body readonly={1}"""

    dct = dict()
    if readonly is not _NOT_SPECIFIED:
      dct['readonly'] = readonly
    resp, obj = self.object_generator.generate_object(
        get_model(obj_type),
        dct,
    )

    self.assertStatus(resp, 201)
    self.assertFalse(obj.readonly)

  @ddt.data(
      ('System', True, True),
      ('System', False, False),
      ('System', None, False),
      ('System', _NOT_SPECIFIED, False),
  )
  @ddt.unpack
  def test_readonly_set_on_post_as_external(self, obj_type, readonly, result):
    """Test flag readonly on {0} POST for body readonly={1} as external user"""

    dct = dict()
    if readonly is not _NOT_SPECIFIED:
      dct['readonly'] = readonly

    with self.object_generator.api.as_external():
      resp, obj = self.object_generator.generate_object(
          get_model(obj_type),
          dct,
      )
      obj_id = obj.id

    self.assertStatus(resp, 201)
    obj = get_model(obj_type).query.get(obj_id)
    self.assertEqual(obj.readonly, result)

  @ddt.data(
      ('System', False, False, 200),
      ('System', False, True, 200),
      ('System', False, None, 200),
      ('System', False, _NOT_SPECIFIED, 200),
      ('System', False, "qwerty", 200),
      ('System', True, False, 405),
      ('System', True, True, 405),
      ('System', True, None, 405),
      ('System', True, _NOT_SPECIFIED, 405),
      ('System', True, "qwerty", 405),
  )
  @ddt.unpack
  def test_put(self, obj_type, current, new, exp_code):
    """Test {0} PUT readonly={2} for current readonly={1}"""

    factory = factories.get_model_factory(obj_type)
    with factories.single_commit():
      obj = factory(title='a', readonly=current)
      obj_id = obj.id

    data = {'title': 'b'}
    if new is not _NOT_SPECIFIED:
      data['readonly'] = new

    resp = self.object_generator.api.put(obj, data)

    self.assertStatus(resp, exp_code)
    obj = get_model(obj_type).query.get(obj_id)
    self.assertEqual(obj.readonly, current)

  @ddt.data(
      ('System', False, False, 200, False),
      ('System', False, True, 200, True),
      ('System', False, None, 200, False),
      ('System', False, _NOT_SPECIFIED, 200, False),
      ('System', True, False, 200, False),
      ('System', True, True, 200, True),
      ('System', True, None, 200, True),
      ('System', True, _NOT_SPECIFIED, 200, True),
  )
  @ddt.unpack
  def test_put_as_external(self, obj_type, current, new, exp_code,
                           exp_readonly):
    """Test {0} PUT readonly={2} for current readonly={1} for external user"""

    factory = factories.get_model_factory(obj_type)
    with factories.single_commit():
      obj = factory(title='a', readonly=current)
      obj_id = obj.id

    data = {'title': 'b'}
    if new is not _NOT_SPECIFIED:
      data['readonly'] = new

    with self.object_generator.api.as_external():
      obj = get_model(obj_type).query.get(obj_id)
      resp = self.object_generator.api.put(obj, data)

    self.assertStatus(resp, exp_code)
    obj = get_model(obj_type).query.get(obj_id)
    self.assertEqual(obj.readonly, exp_readonly)

  @ddt.data('System')
  def test_403_if_put_readonly_without_perms(self, obj_type):
    """Test {0} with readonly=True PUT returns 401 instead of 405

    This test ensures that user without permission for the object
    cannot obtain value for flag readonly
    """
    role_obj = all_models.Role.query.filter(
        all_models.Role.name == "Creator").one()

    factory = factories.get_model_factory(obj_type)

    with factories.single_commit():
      # create Global Creator
      person = factories.PersonFactory()
      person_id = person.id
      rbac_factories.UserRoleFactory(role=role_obj, person=person)

      # Create object
      obj = factory(title='a', readonly=True)
      obj_id = obj.id

    self.object_generator.api.set_user(all_models.Person.query.get(person_id))
    obj = get_model(obj_type).query.get(obj_id)
    resp = self.object_generator.api.put(obj, {'title': 'b'})

    self.assert403(resp)

  @ddt.data(
      ('System', True, False, 200, True),
      ('System', True, True, 405, False),
      ('System', False, False, 200, True),
      ('System', False, True, 405, False),
  )
  @ddt.unpack
  def test_delete(self, obj_type, is_external, readonly, exp_code,
                  exp_deleted):
    """Test {0} DELETE if readonly={1}"""

    factory = factories.get_model_factory(obj_type)
    with factories.single_commit():
      obj = factory(title='a', readonly=readonly)
      obj_id = obj.id

    if is_external:
      self.object_generator.api.login_as_external()
    else:
      self.object_generator.api.login_as_normal()

    obj = get_model(obj_type).query.get(obj_id)
    resp = self.object_generator.api.delete(obj)

    self.assertStatus(resp, exp_code)
    obj = get_model(obj_type).query.get(obj_id)
    if exp_deleted:
      self.assertIsNone(obj)
    else:
      self.assertIsNotNone(obj)

  @ddt.data('System')
  def test_403_if_delete_readonly_without_perms(self, obj_type):
    """Test {0} with readonly=True DELETE returns 401

    This test ensures that user without permission for the object
    cannot obtain value for flag readonly
    """

    role_obj = all_models.Role.query.filter(
        all_models.Role.name == "Creator").one()

    factory = factories.get_model_factory(obj_type)

    with factories.single_commit():
      # create Global Creator
      person = factories.PersonFactory()
      person_id = person.id
      rbac_factories.UserRoleFactory(role=role_obj, person=person)

      # Create object
      obj = factory(title='a', readonly=True)
      obj_id = obj.id

    self.object_generator.api.set_user(all_models.Person.query.get(person_id))
    obj = get_model(obj_type).query.get(obj_id)
    resp = self.object_generator.api.delete(obj)

    self.assert403(resp)
    obj = get_model(obj_type).query.get(obj_id)
    self.assertIsNotNone(obj)

  @ddt.data(
      ('System', False, 'Document', True, 201),
      ('System', False, 'Document', False, 201),
      ('System', True, 'Document', True, 405),
      ('System', True, 'Document', False, 405),
      ('System', False, 'Comment', True, 201),
      ('System', False, 'Comment', False, 201),
      ('System', True, 'Comment', True, 201),
      ('System', True, 'Comment', False, 201),
  )
  @ddt.unpack
  def test_relationship_post(self, obj_type, readonly, rel_obj_type, swap,
                             expected_code):
    """Test PUT relationship {0}.readonly={1}, related object type {2}"""

    factory = factories.get_model_factory(obj_type)
    rel_factory = factories.get_model_factory(rel_obj_type)
    with factories.single_commit():
      obj = factory(title='a', readonly=readonly)
      rel_obj = rel_factory()

    if swap:
      source, destination = rel_obj, obj
    else:
      source, destination = obj, rel_obj

    resp, _ = self.object_generator.generate_relationship(
        source=source, destination=destination
    )

    self.assertStatus(resp, expected_code)

  @ddt.data(
      ('System', False, 'Document', True, 200),
      ('System', False, 'Document', False, 200),
      ('System', True, 'Document', True, 405),
      ('System', True, 'Document', False, 405),
      ('System', False, 'Comment', True, 200),
      ('System', False, 'Comment', False, 200),
      ('System', True, 'Comment', True, 200),
      ('System', True, 'Comment', False, 200),
  )
  @ddt.unpack
  def test_relationship_delete(self, obj_type, readonly, rel_obj_type, swap,
                               expected_code):
    """Test DELETE relationship {0}.readonly={1}, related object type {2}"""

    factory = factories.get_model_factory(obj_type)
    rel_factory = factories.get_model_factory(rel_obj_type)
    with factories.single_commit():
      obj = factory(title='a', readonly=readonly)
      rel_obj = rel_factory()

      if swap:
        source, destination = rel_obj, obj
      else:
        source, destination = obj, rel_obj

      robj = factories.RelationshipFactory(source=source,
                                           destination=destination)

    resp = self.object_generator.api.delete(robj)

    self.assertStatus(resp, expected_code)

  @ddt.data(
      ("yes", "readonly system"),
      ("no", "non readonly system"),
  )
  @ddt.unpack
  def test_readonly_searchable(self, test_value, expected_title):
    """Test filtration by readonly attribute"""
    with factories.single_commit():
      factories.SystemFactory(title="readonly system", readonly=True)
      factories.SystemFactory(title="non readonly system")

    self.client.get("/login")
    actual_systems = self.simple_query(
        "System",
        expression=["readonly", "=", test_value]
    )
    self.assertEqual(
        [s.get("title") for s in actual_systems],
        [expected_title]
    )


@ddt.ddt
class TestWithReadOnlyAccessImport(TestCase):
  """Test for metrics import."""

  def setUp(self):
    super(TestWithReadOnlyAccessImport, self).setUp()
    self.api = api_helper.Api()
    self.client.get("/login")

  @ddt.data(
      ("yes", True),
      ("no", False),
      (None, False),
      ("", False),
  )
  @ddt.unpack
  def test_system_create_with_readonly_set(self, readonly, expected):
    """Test flag readonly={0} for new System"""

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", "CODE"),
        ("Admin", "user@example.com"),
        ("Assignee", "user@example.com"),
        ("Verifier", "user@example.com"),
        ("Title", "b"),
    ])
    if readonly is not None:
      data["Read-only"] = readonly

    response = self.import_data(data)
    self._check_csv_response(response, {})
    obj = get_model("System").query.one()
    self.assertEqual(obj.readonly, expected)

  def test_system_create_with_invalid_readonly(self):
    """Test invalid readonly value for new System"""

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", "CODE"),
        ("Admin", "user@example.com"),
        ("Assignee", "user@example.com"),
        ("Verifier", "user@example.com"),
        ("Title", "b"),
        ("Read-only", "qwerty")
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {
        "System": {
            "row_warnings": {
                errors.WRONG_VALUE.format(line=3, column_name="Read-only")
            },
        }
    })
    obj = get_model("System").query.one()
    self.assertFalse(obj.readonly)

  @ddt.data(
      ("no", False),
      ("yes", True),
      (None, False),
      ("", False),
  )
  @ddt.unpack
  def test_system_update_to_readonly_as_admin(self, new, expected):
    """Test System readonly={1} if new={0}"""

    with factories.single_commit():
      obj = factories.SystemFactory(title='a', readonly=False)

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("Title", "b"),
    ])
    if new is not None:
      data["Read-only"] = new

    response = self.import_data(data)
    self._check_csv_response(response, {})
    obj = get_model("System").query.one()
    self.assertEqual(obj.readonly, expected)

  def test_system_not_updated_as_admin(self):
    """Test readonly System not updated by admin"""

    with factories.single_commit():
      obj = factories.SystemFactory(title='a', readonly=True)

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("Title", "b"),
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {
        "System": {
            "row_warnings": {
                errors.READONLY_ACCESS_WARNING.format(
                    line=3, columns="'Title'"),
            },
        }
    })
    obj = get_model("System").query.one()
    self.assertEqual(obj.readonly, True)
    self.assertEqual(obj.title, 'a')

  def test_system_update_and_unset_readonly_as_admin(self):
    """Test System readonly unset and title updated by admin in same import"""

    with factories.single_commit():
      obj = factories.SystemFactory(title='a', readonly=True)

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("Title", "b"),
        ("Read-Only", "no"),
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {})
    obj = get_model("System").query.one()
    self.assertEqual(obj.readonly, False)
    self.assertEqual(obj.title, 'b')

  @ddt.data("no", "yes", _NOT_SPECIFIED, "", True)
  def test_user_cannot_get_readonly_value_without_perms(self, new):
    """Test readonly System not updated if new={0!r} and user has no perms

    This test ensures that user without permission for the object
    cannot obtain value for flag readonly
    """

    role_obj = all_models.Role.query.filter(
        all_models.Role.name == "Creator").one()

    with factories.single_commit():
      person = factories.PersonFactory()
      person_id = person.id
      rbac_factories.UserRoleFactory(role=role_obj, person=person)

      obj = factories.SystemFactory(title='a', readonly=True)

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("Title", "b"),
    ])
    if new is not _NOT_SPECIFIED:
      data["Read-only"] = new

    response = self.import_data(
        data,
        person=all_models.Person.query.get(person_id)
    )
    exp_csv_responsse = {
        "System": {
            "row_errors": {
                errors.PERMISSION_ERROR.format(line=3),
            },
        }
    }
    if new is not _NOT_SPECIFIED:
      exp_csv_responsse['System']['row_warnings'] = {
          errors.NON_ADMIN_ACCESS_ERROR.format(
              line=3,
              object_type="System",
              column_name="Read-only",
          ),
      }

    self._check_csv_response(response, exp_csv_responsse)

    obj = get_model("System").query.one()
    self.assertEqual(obj.readonly, True)
    self.assertEqual(obj.title, 'a')

  def test_system_readonly_invalid_on_update(self):
    """Test System readonly=False on update with invalid data"""

    with factories.single_commit():
      obj = factories.SystemFactory(title='a', readonly=False)

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("Title", "b"),
        ("Read-only", "qwerty")
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {
        "System": {
            "row_warnings": {
                errors.WRONG_VALUE.format(line=3, column_name="Read-only")
            },
        }
    })
    obj = get_model("System").query.one()
    self.assertFalse(obj.readonly)

  def test_readonly_system_not_deleted(self):
    """Test System with readonly=True can be deleted"""

    with factories.single_commit():
      obj = factories.SystemFactory(title='a', readonly=True)
      obj_id = obj.id

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("Delete", "yes"),
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {
        "System": {
            "row_warnings": {
                errors.READONLY_ACCESS_WARNING.format(line=3,
                                                      columns="'Delete'"),
            },
        }
    })
    obj = get_model("System").query.get(obj_id)
    self.assertIsNotNone(obj)

  def test_readonly_system_not_deleted_without_user_perms(self):
    """Test System with readonly=True can be deleted

    This test ensures that user without permission for the object
    cannot obtain value for flag readonly
    """

    role_obj = all_models.Role.query.filter(
        all_models.Role.name == "Creator").one()

    with factories.single_commit():
      person = factories.PersonFactory()
      person_id = person.id
      rbac_factories.UserRoleFactory(role=role_obj, person=person)

      obj = factories.SystemFactory(title='a', readonly=True)
      obj_id = obj.id

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("Delete", "yes"),
    ])

    response = self.import_data(
        data,
        person=all_models.Person.query.get(person_id)
    )
    self._check_csv_response(response, {
        "System": {
            "row_errors": {
                "Line 3: Delete column is temporary disabled, please "
                "use web interface to delete current object.",
                errors.PERMISSION_ERROR.format(line=3),
            },
        }
    })
    obj = get_model("System").query.get(obj_id)
    self.assertIsNotNone(obj)

  @ddt.data(
      ("yes", ['c1', 'c2'], ['c1', 'c2']),
      ("no", ['c1', 'c2'], ['c1', 'c2']),
  )
  @ddt.unpack
  def test_system_add_comments_on_post(self, readonly, comments, exp_comments):
    """Test Comment creation {1} on post System with readonly={0}"""

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", "CODE"),
        ("Admin", "user@example.com"),
        ("Assignee", "user@example.com"),
        ("Verifier", "user@example.com"),
        ("Title", "b"),
        ("Read-only", readonly),
        ("Comments", ';;'.join(comments)),
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {})

    obj = get_model("System").query.one()
    created_comments = set(comment.description
                           for comment in obj.related_objects(['Comment']))
    self.assertEqual(created_comments, set(exp_comments))

  @ddt.data(
      (True, ['c1', 'c2'], ['c1', 'c2']),
      (False, ['c1', 'c2'], ['c1', 'c2']),
  )
  @ddt.unpack
  def test_system_add_comments_on_update(self, readonly, comments,
                                         exp_comments):
    """Test Comment creation {1} on update System with readonly={0}"""

    with factories.single_commit():
      obj = factories.SystemFactory(title='a', readonly=readonly)

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("Comments", ';;'.join(comments)),
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {})

    obj = get_model("System").query.one()
    created_comments = set(comment.description
                           for comment in obj.related_objects(['Comment']))
    self.assertEqual(created_comments, set(exp_comments))

  @ddt.data(
      ("yes", True),
      ("no", True),
  )
  @ddt.unpack
  def test_system_add_document_on_post(self, readonly, exp_set):
    """Test Reference URL, URL for Ariane and URL for SPUR
    set on post System with readonly={0}"""

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", "CODE"),
        ("Admin", "user@example.com"),
        ("Assignee", "user@example.com"),
        ("Verifier", "user@example.com"),
        ("Title", "b"),
        ("Read-only", readonly),
        ("Reference URL", "aa"),
        ("URL for Ariane", "bb"),
        ("URL for SPUR", "cc"),
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {})

    obj = get_model("System").query.one()
    docs = obj.documents_reference_url

    if exp_set:
      self.assertEqual(len(docs), 1)
      doc = docs[0]
      self.assertEqual(doc.link, "aa")
    else:
      self.assertEqual(len(docs), 0)

  @ddt.data(
      (True, False),
      (False, True),
  )
  @ddt.unpack
  def test_system_add_document_on_update(self, readonly, exp_set):
    """Test Reference URL set on update System with readonly={0}"""

    with factories.single_commit():
      obj = factories.SystemFactory(title='a', readonly=readonly)

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("Reference URL", "aa"),
    ])

    if exp_set:
      dct = {}
    else:
      dct = {
          "System": {
              "row_warnings": {
                  errors.READONLY_ACCESS_WARNING.format(
                      line=3, columns="'Reference URL'"),
              },
          }
      }

    response = self.import_data(data)
    self._check_csv_response(response, dct)

    obj = get_model("System").query.one()
    docs = obj.documents_reference_url

    if exp_set:
      self.assertEqual(len(docs), 1)
      doc = docs[0]
      self.assertEqual(doc.link, "aa")
    else:
      self.assertEqual(len(docs), 0)

  @ddt.data(
      ("yes", 'Program'),
      ("no", 'Program'),
      ("yes", 'System'),
      ("no", 'System'),
  )
  @ddt.unpack
  def test_system_map_on_post(self, readonly, rel_obj_type):
    """Test mapping on post System with readonly={0}"""

    rel_factory = factories.get_model_factory(rel_obj_type)
    with factories.single_commit():
      rel_obj = rel_factory()
      rel_obj_id = rel_obj.id

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", "CODE"),
        ("Admin", "user@example.com"),
        ("Assignee", "user@example.com"),
        ("Verifier", "user@example.com"),
        ("Title", "b"),
        ("Read-only", readonly),
        ("map:{}".format(rel_obj_type), rel_obj.slug),
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {})

    obj = get_model("System").query.filter_by(slug="CODE").one()
    rel_ids = list(o.id for o in obj.related_objects([rel_obj_type]))

    self.assertIn(rel_obj_id, rel_ids)

  @ddt.data(
      (True, 'Program'),
      (False, 'Program'),
      (True, 'System'),
      (False, 'System'),
  )
  @ddt.unpack
  def test_system_map_on_update(self, readonly, rel_obj_type):
    """Test mapping on update System with readonly={0}"""

    rel_factory = factories.get_model_factory(rel_obj_type)
    with factories.single_commit():
      obj = factories.SystemFactory(title='a', readonly=readonly)
      obj_id = obj.id

      rel_obj = rel_factory()
      rel_obj_id = rel_obj.id

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("map:{}".format(rel_obj_type), rel_obj.slug),
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {})

    obj = get_model("System").query.get(obj_id)
    rel_obj = get_model(rel_obj_type).query.get(rel_obj_id)
    rel = all_models.Relationship.find_related(obj, rel_obj)
    self.assertIsNotNone(rel)

  @ddt.data(
      (True, 'Program'),
      (False, 'Program'),
      (True, 'System'),
      (False, 'System'),
  )
  @ddt.unpack
  def test_system_unmap_on_update(self, readonly, rel_obj_type):
    """Test unmapping on update System with readonly={0}"""

    rel_factory = factories.get_model_factory(rel_obj_type)
    with factories.single_commit():
      obj = factories.SystemFactory(title='a', readonly=readonly)
      obj_id = obj.id

      rel_obj = rel_factory()
      rel_obj_id = rel_obj.id

      factories.RelationshipFactory(source=obj, destination=rel_obj)

    data = OrderedDict([
        ("object_type", "System"),
        ("Code*", obj.slug),
        ("unmap:{}".format(rel_obj_type), rel_obj.slug),
    ])

    response = self.import_data(data)
    self._check_csv_response(response, {})

    obj = get_model("System").query.get(obj_id)
    rel_obj = get_model(rel_obj_type).query.get(rel_obj_id)
    rel = all_models.Relationship.find_related(obj, rel_obj)
    self.assertIsNone(rel)

  @ddt.data(
      ("Creator", False),
      ("Reader", False),
      ("Editor", False),
      ("Administrator", True),
  )
  @ddt.unpack
  def test_readonly_set_by_role(self, role_name, expected_readonly):
    """Test setting Read-only to true under {}."""
    role_obj = all_models.Role.query.filter(
        all_models.Role.name == role_name
    ).one()

    with factories.single_commit():
      user = factories.PersonFactory()
      rbac_factories.UserRoleFactory(role=role_obj, person=user)

    response = self.import_data(OrderedDict([
        ("object_type", "System"),
        ("Code*", "System-1"),
        ("Admin", user.email),
        ("Assignee", user.email),
        ("Verifier", user.email),
        ("Title", "New System"),
        ("Read-only", True),
    ]), person=user)

    expected_warning = {
        "System": {
            "row_warnings": {
                errors.NON_ADMIN_ACCESS_ERROR.format(
                    line=3,
                    object_type="System",
                    column_name="Read-only"
                )
            }
        }
    } if role_name != "Administrator" else {}
    self._check_csv_response(response, expected_warning)

    obj = all_models.System.query.filter_by(slug="System-1").first()
    self.assertEqual(obj.readonly, expected_readonly)

  @ddt.data(
      ("Creator", True),
      ("Reader", True),
      ("Editor", True),
      ("Administrator", False),
  )
  @ddt.unpack
  def test_readonly_unset_by_role(self, role_name, expected_readonly):
    """Test setting Read-only to false under {}."""
    role_obj = all_models.Role.query.filter(
        all_models.Role.name == role_name
    ).one()

    with factories.single_commit():
      user = factories.PersonFactory()
      system = factories.SystemFactory(readonly=True)
      rbac_factories.UserRoleFactory(role=role_obj, person=user)
      system.add_person_with_role_name(user, "Admin")

      system_slug = system.slug
      user_id = user.id

    response = self.import_data(OrderedDict([
        ("object_type", "System"),
        ("Code*", system_slug),
        ("Read-only", "no"),
    ]), person=all_models.Person.query.get(user_id))

    expected_warning = {
        "System": {
            "row_warnings": {
                errors.NON_ADMIN_ACCESS_ERROR.format(
                    line=3,
                    object_type="System",
                    column_name="Read-only"
                )
            }
        }
    } if expected_readonly else {}
    self._check_csv_response(response, expected_warning)

    obj = all_models.System.query.filter_by(slug=system_slug).first()
    self.assertEqual(obj.readonly, expected_readonly)

  @ddt.data(
      ("Creator", False, True),
      ("Reader", False, True),
      ("Editor", False, True),
      ("Administrator", False, True),
  )
  @ddt.unpack
  def test_readonly_update_by_role(self, role, old_readonly, new_readonly):
    """Test updating readonly attribute from {1} to {2} as {0}."""
    role_obj = all_models.Role.query.filter(
        all_models.Role.name == role
    ).one()

    with factories.single_commit():
      user = factories.PersonFactory()
      system = factories.SystemFactory(readonly=old_readonly)
      rbac_factories.UserRoleFactory(role=role_obj, person=user)
      system.add_person_with_role_name(user, "Admin")

    response = self.import_data(OrderedDict([
        ("object_type", "System"),
        ("Code*", system.slug),
        ("Admin", user.email),
        ("Read-only", new_readonly),
    ]), person=user)

    expected_message = {
        "System": {
            "row_warnings": {
                errors.NON_ADMIN_ACCESS_ERROR.format(
                    line=3,
                    column_name="Read-only",
                    object_type="System",
                )
            }
        }
    } if role != "Administrator" else {}
    self._check_csv_response(response, expected_message)

    obj = all_models.System.query.get(system.id)
    self.assertEqual(
        obj.readonly,
        new_readonly if role == "Administrator" else old_readonly
    )


@ddt.ddt
class TestWithReadOnlyAccessFolder(TestCase):
  """Test for "unmap_objects" view."""

  NOT_PRESENT = object()
  PATH_ADD_FOLDER = '/api/add_folder'
  PATH_REMOVE_FOLDER = '/api/remove_folder'

  FOLDERABLE_MODEL_NAMES = list(m.__name__ for m in all_models.all_models
                                if issubclass(m, mixins.Folderable) and
                                m not in (all_models.Directive,
                                          all_models.SystemOrProcess))

  def setUp(self):
    """setUp"""
    super(TestWithReadOnlyAccessFolder, self).setUp()
    self.api = api_helper.Api()

  def _get_request_data(self, obj_type=NOT_PRESENT, obj_id=NOT_PRESENT,
                        folder=NOT_PRESENT):
    """Prepare request dict"""
    dct = dict()

    if obj_type is not self.NOT_PRESENT:
      dct['object_type'] = obj_type

    if obj_id is not self.NOT_PRESENT:
      dct['object_id'] = obj_id

    if folder is not self.NOT_PRESENT:
      dct['folder'] = folder

    return json.dumps(dct)

  @ddt.data(
      ('System', 'Creator', 403),
      ('System', 'Reader', 403),
      ('System', 'Editor', 405),
      ('System', 'Administrator', 405),
  )
  @ddt.unpack
  def test_readonly_add_folder_with_global_role(self, obj_type, role_name,
                                                expected_status):
    """Test add_folder read-only {0} by user with global role {1}"""

    role_obj = all_models.Role.query.filter(
        all_models.Role.name == role_name).one()

    factory = factories.get_model_factory(obj_type)
    with factories.single_commit():
      obj_id = factory(folder="a", readonly=True).id
      person = factories.PersonFactory()
      rbac_factories.UserRoleFactory(role=role_obj, person=person)
      person_id = person.id

    self.api.set_user(all_models.Person.query.get(person_id))

    response = self.api.client.post(
        self.PATH_ADD_FOLDER, content_type="application/json",
        data=self._get_request_data(obj_type, obj_id, folder="b"))

    self.assertStatus(response, expected_status)
    obj = get_model(obj_type).query.get(obj_id)
    self.assertEqual(obj.folder, "a")

  @ddt.data(
      ('System', 'Creator', 403),
      ('System', 'Reader', 403),
      ('System', 'Editor', 405),
      ('System', 'Administrator', 405),
  )
  @ddt.unpack
  def test_readonly_remove_folder_with_global_role(self, obj_type, role_name,
                                                   expected_status):
    """Test remove_folder read-only {0} by user with global role {1}"""

    role_obj = all_models.Role.query.filter(
        all_models.Role.name == role_name).one()

    factory = factories.get_model_factory(obj_type)
    with factories.single_commit():
      obj_id = factory(folder="a", readonly=True).id
      person = factories.PersonFactory()
      rbac_factories.UserRoleFactory(role=role_obj, person=person)
      person_id = person.id

    self.api.set_user(all_models.Person.query.get(person_id))

    response = self.api.client.post(
        self.PATH_REMOVE_FOLDER, content_type="application/json",
        data=self._get_request_data(obj_type, obj_id, folder="a"))

    self.assertStatus(response, expected_status)
    obj = get_model(obj_type).query.get(obj_id)
    self.assertEqual(obj.folder, "a")


@ddt.ddt
class TestWithReadOnlyAccessExport(TestCase):
  """Test for exporting objects with read-only access."""

  def setUp(self):
    """setUp"""
    super(TestWithReadOnlyAccessExport, self).setUp()
    self.api = api_helper.Api()
    self.client.get("/login")

  def test_export_system(self):
    """Test exporting of System objects."""
    factories.SystemFactory()

    search_request = [{
        "object_name": "System",
        "fields": "all",
        "filters": {
            "expression": {}
        }
    }]

    response = self.export_parsed_csv(search_request)
    self.assertEqual(len(response["System"]), 1)
    self.assertNotIn("Read-only", response["System"][0])
    self.assertNotIn("readonly", response["System"][0])

  def test_export_system_template(self):
    """Test exporting of System import template."""
    response = self.export_csv_template([{"object_name": "System"}])
    self.assertNotIn("Read-only", response.data)
    self.assertNotIn("readonly", response.data)

  def test_export_system_attributes(self):
    """Test that Read-only flag is not show on export page."""
    export_attributes = views.get_all_attributes_json()
    self.assertNotIn("Read-only", export_attributes)
    self.assertNotIn("readonly", export_attributes)
    self.assertNotIn("hidden", export_attributes)
