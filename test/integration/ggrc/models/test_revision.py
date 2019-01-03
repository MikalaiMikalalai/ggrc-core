# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

""" Tests for ggrc.models.Revision """
import ddt
import mock

import ggrc.models
from ggrc.models import all_models
import integration.ggrc.generator
from integration.ggrc import TestCase

from integration.ggrc.models import factories
from integration.ggrc import api_helper
from integration.ggrc.review import build_reviewer_acl


def _get_revisions(obj, field="resource"):
  return ggrc.models.Revision.query.filter_by(**{
      field + "_type": obj.__class__.__name__,
      field + "_id": obj.id
  }).all()


def _project_content(content):
  return {
      "source": {
          "type": content["source_type"],
          "id": content["source_id"],
      },
      "destination": {
          "type": content["destination_type"],
          "id": content["destination_id"],
      },
  }


@ddt.ddt
class TestRevisions(TestCase):
  """ Tests for ggrc.models.Revision """

  def setUp(self):
    super(TestRevisions, self).setUp()
    self.gen = integration.ggrc.generator.ObjectGenerator()
    self.api_helper = api_helper.Api()
    self.api_helper.client.get("/login")

  def test_revisions(self):
    """ Test revision creation for POST and PUT """
    cls = ggrc.models.DataAsset
    name = cls._inflector.table_singular  # pylint: disable=protected-access
    _, obj = self.gen.generate(cls, name, {name: {
        "title": "revisioned v1",
        "context": None,
    }})
    revisions = _get_revisions(obj)
    self.assertEqual(len(revisions), 1)

    _, obj = self.gen.modify(obj, name, {name: {
        "slug": obj.slug,
        "title": "revisioned v2",
        "context": None,
    }})
    revisions = _get_revisions(obj)
    expected = {("created", "revisioned v1"), ("modified", "revisioned v2")}
    actual = {(r.action, r.content["title"]) for r in revisions}
    self.assertEqual(actual, expected)

  def test_relevant_revisions(self):
    """ Test revision creation for mapping to an object """
    cls = ggrc.models.DataAsset
    name = cls._inflector.table_singular  # pylint: disable=protected-access

    _, obj1 = self.gen.generate(cls, name, {name: {
        "title": "connected 1",
        "context": None,
    }})

    _, obj2 = self.gen.generate(cls, name, {name: {
        "title": "connected 2",
        "context": None,
    }})

    rel_data = {
        "source": {"id": obj1.id, "type": cls.__name__},
        "destination": {"id": obj2.id, "type": cls.__name__},
        "context": None,
    }
    _, rel = self.gen.generate(ggrc.models.Relationship, "relationship", {
                               "relationship": rel_data})

    revisions_source = _get_revisions(obj1, "source")
    revisions_destination = _get_revisions(obj2, "destination")

    self.assertEqual(revisions_source, revisions_destination)
    self.assertEqual(len(revisions_source), 1)

    self.gen.api.delete(rel)

    revisions_source = _get_revisions(obj1, "source")
    revisions_destination = _get_revisions(obj2, "destination")

    self.assertEqual(revisions_source, revisions_destination)
    self.assertEqual(len(revisions_source), 2)

    expected_data = {
        "source": {
            "type": cls.__name__,
            "id": obj1.id,
        },
        "destination": {
            "type": cls.__name__,
            "id": obj2.id,
        },
    }
    expected = [(u"created", expected_data), ("deleted", expected_data)]

    actual = [(r.action, _project_content(r.content))
              for r in revisions_source]
    self.assertEqual(sorted(actual), sorted(expected))

  def test_content_length(self):
    """Test revision content length restrictions."""
    process = factories.ProcessFactory(
        title="a" * 200,
        description="b" * 65000,
        notes="c" * 65000,
    )
    revision = ggrc.models.Revision.query.filter(
        ggrc.models.Revision.resource_id == process.id,
        ggrc.models.Revision.resource_type == process.type,
    ).first()
    self.assertIsNotNone(revision)
    self.assertEqual(revision.content["title"], process.title)
    self.assertEqual(revision.content["description"], process.description)

  @ddt.data(True, False)
  def test_revision_after_del_cad(self, is_add_cav):
    """Test creating new revision after deleting CAD.

    In case of deleting CAD, new revision must be created for object,
    which had this CAD.
    """
    with factories.single_commit():
      control = factories.ControlFactory()

      cad = factories.CustomAttributeDefinitionFactory(
          title="test_name",
          definition_type="control",
      )
      if is_add_cav:
        factories.CustomAttributeValueFactory(
            custom_attribute=cad,
            attributable=control,
            attribute_value="text",
        )

      revision_id = ggrc.models.Revision.query.filter(
          ggrc.models.Revision.resource_id == control.id,
          ggrc.models.Revision.resource_type == control.type,
      ).order_by(ggrc.models.Revision.id.desc()).first().id

    self.api_helper.delete(cad)

    control = ggrc.models.Control.query.first()

    last_revision_id = ggrc.models.Revision.query.filter(
        ggrc.models.Revision.resource_id == control.id,
        ggrc.models.Revision.resource_type == control.type,
    ).order_by(ggrc.models.Revision.id.desc()).first().id

    self.assertGreater(last_revision_id, revision_id)

  @ddt.data(True, False)
  def test_change_modified_by(self, is_add_cav):
    """Test checked correct changing of modified_by_id field.

    User 1 create control, user 2 delete CAD. After the deleting CAD
    test checking that modified_by field contains user 2.
    """
    with factories.single_commit():
      control = factories.ControlFactory()
      cad = factories.CustomAttributeDefinitionFactory(
          title="test_cad",
          definition_type="control",
          attribute_type="Text",
      )
      control_id = control.id
      if is_add_cav:
        factories.CustomAttributeValueFactory(
            custom_attribute=cad,
            attributable=control,
            attribute_value="test")

    user = self.gen.generate_person(
        data={"name": "test_admin"}, user_role="Administrator")[1]
    self.api_helper.set_user(user)
    self.client.get("/login")

    control_revisions = ggrc.models.Revision.query.filter(
        ggrc.models.Revision.resource_id == control_id,
        ggrc.models.Revision.resource_type == "Control",
    ).order_by(ggrc.models.Revision.id.desc()).all()
    ids_before_del = set(revision.id for revision in control_revisions)

    cad = ggrc.models.CustomAttributeDefinition.query.filter_by(
        title="test_cad").first()
    resp_delete = self.api_helper.delete(cad)
    self.assert200(resp_delete)
    cad = ggrc.models.CustomAttributeDefinition.query.filter_by(
        title="test_cad").first()
    self.assertIsNone(cad)

    control_revisions_after = ggrc.models.Revision.query.filter(
        ggrc.models.Revision.resource_id == control_id,
        ggrc.models.Revision.resource_type == "Control",
    ).order_by(ggrc.models.Revision.id.desc()).all()
    ids_after_del = set(revision.id for revision
                        in control_revisions_after)

    difference_revision_id = ids_after_del.difference(ids_before_del)

    last_revision = ggrc.models.Revision.query.filter(
        ggrc.models.Revision.resource_id == control_id,
        ggrc.models.Revision.resource_type == "Control",
    ).order_by(ggrc.models.Revision.id.desc()).first()

    self.assertSetEqual(difference_revision_id, {last_revision.id})

    expected_id = ggrc.models.Person.query.filter_by(
        name="test_admin").first().id

    self.assertEquals(last_revision.content["modified_by_id"], expected_id)
    self.assertEquals(last_revision.content["modified_by"]["id"], expected_id)

  def _test_revision_with_empty_cads(self,
                                     attribute_type,
                                     attribute_value,
                                     is_global):
    """Population cavs and cads depend on is_global flag and send params."""
    asmnt = factories.AssessmentFactory()
    asmnt_id = asmnt.id
    cad_params = {
        "title": "test_cad",
        "definition_type": "assessment",
        "attribute_type": attribute_type
    }
    if not is_global:
      cad_params["definition_id"] = asmnt_id
    with factories.single_commit():
      cad = factories.CustomAttributeDefinitionFactory(**cad_params)
    cad_id = cad.id
    revisions = ggrc.models.Revision.query.filter(
        ggrc.models.Revision.resource_id == asmnt_id,
        ggrc.models.Revision.resource_type == "Assessment",
    ).order_by(ggrc.models.Revision.id.desc()).all()
    self.assertEqual(1, len(revisions))
    revision = revisions[0]
    # pylint: disable=protected-access
    self.assertIn("custom_attribute_values", revision._content)
    self.assertIn("custom_attribute_definitions", revision._content)
    self.assertEqual([], revision._content["custom_attribute_values"])
    self.assertEqual([], revision._content["custom_attribute_definitions"])
    self.assertIn("custom_attribute_values", revision.content)
    self.assertEqual(
        [{
            'attributable_id': asmnt_id,
            'attributable_type': 'Assessment',
            'attribute_object': None,
            'attribute_value': attribute_value,
            'context_id': None,
            'custom_attribute_id': cad_id,
            'display_name': '',
            'type': 'CustomAttributeValue',
        }],
        revision.content["custom_attribute_values"])
    self.assertIn("custom_attribute_definitions", revision.content)
    cad = all_models.CustomAttributeDefinition.query.get(cad_id)
    self.assertEqual([cad.log_json()],
                     revision.content["custom_attribute_definitions"])

  @ddt.data(
      ("Text", ""),
      ("Rich Text", ""),
      ("Dropdown", ""),
      ("Checkbox", "0"),
      ("Date", ""),
      ("Map:Person", "Person"),
  )
  @ddt.unpack
  def test_revisions_with_empty_gcads(self, attribute_type, attribute_value):
    """Population cavs and global cads for type {0}."""
    self._test_revision_with_empty_cads(attribute_type, attribute_value, True)

  @ddt.data(
      ("Text", ""),
      ("Rich Text", ""),
      ("Dropdown", ""),
      ("Checkbox", "0"),
      ("Date", ""),
      ("Map:Person", "Person"),
  )
  @ddt.unpack
  def test_revisions_with_empty_lcads(self, attribute_type, attribute_value):
    """Population cavs and local cads for type {0}."""
    self._test_revision_with_empty_cads(attribute_type, attribute_value, False)

  @ddt.data("", u"0", u"", None, "0")
  @mock.patch(
      "ggrc.models.custom_attribute_value.CustomAttributeValue"
      "._validate_checkbox", return_value=True
  )
  def test_revisions_invalid_cavs(self, value, _):
    """Test filtering of Checkbox CAVs."""
    with factories.single_commit():
      asmnt = factories.AssessmentFactory()
      ca_def = factories.CustomAttributeDefinitionFactory(
          definition_id=asmnt.id,
          definition_type="assessment",
          title="CA",
          attribute_type="Checkbox",
      )

    self.gen.api.modify_object(
        asmnt, {
            "custom_attribute_values": [{
                "attributable_id": asmnt.id,
                "attributable_type": "assessment",
                "attribute_value": value,
                "custom_attribute_id": ca_def.id,
            }, ],
        },
    )
    revisions = ggrc.models.Revision.query.filter(
        ggrc.models.Revision.resource_id == asmnt.id,
        ggrc.models.Revision.resource_type == "Assessment",
    ).order_by(ggrc.models.Revision.id.desc()).all()
    content = revisions[0].content
    self.assertEqual(
        content["custom_attribute_values"][0]["attribute_value"], "0")

  def test_revision_review_stub(self):
    """ Test proper review stub population in revision content """
    control = factories.ControlFactory()
    revisions = _get_revisions(control)
    self.assertEqual(len(revisions), 1)
    self.assertEqual(revisions[0].action, "created")

    resp = self.api_helper.post(
        all_models.Review,
        {
            "review": {
                "reviewable": {
                    "type": control.type,
                    "id": control.id,
                },
                "context": None,
                "notification_type": "email",
                "status": all_models.Review.STATES.REVIEWED,
                "access_control_list": build_reviewer_acl()
            },
        },
    )
    self.assertEqual(201, resp.status_code)
    self.assertIn("review", resp.json)
    resp_review = resp.json["review"]
    self.assertEqual(all_models.Review.STATES.REVIEWED,
                     resp_review["status"])

    revisions = _get_revisions(control)
    self.assertEqual(len(revisions), 2)
    self.assertEqual(revisions[0].action, "created")
    self.assertEqual(revisions[1].action, "modified")

    rev_content = revisions[1].content
    self.assertIsNotNone(rev_content)
    self.assertIn("review", rev_content)
    review = rev_content["review"]
    self.assertIsNotNone(review)

    expected = {
        "context_id": None,
        "href": "/api/reviews/{}".format(resp_review["id"]),
        "id": resp_review["id"],
        "type": resp_review["type"],
    }

    self.assertEqual(review, expected)
