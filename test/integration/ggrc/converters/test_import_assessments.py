# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

# pylint: disable=maybe-no-member, invalid-name, too-many-lines

"""Test request import and updates."""

import unittest
import datetime
from collections import OrderedDict

import ddt
import freezegun

from ggrc import db
from ggrc import utils
from ggrc.models import all_models
from ggrc.access_control.role import get_custom_roles_for
from ggrc.converters import errors

from integration.ggrc import TestCase
from integration.ggrc.generator import ObjectGenerator
from integration.ggrc.models import factories


# pylint: disable=too-many-public-methods
@ddt.ddt
class TestAssessmentImport(TestCase):
  """Basic Assessment import tests with.

  This test suite should test new Assessment imports, exports, and updates.
  The main focus of these tests is checking error messages for invalid state
  transitions.
  """

  def setUp(self):
    """Set up for Assessment test cases."""
    super(TestAssessmentImport, self).setUp()
    self.client.get("/login")

  def test_import_assessments_with_templates(self):
    """Test importing of assessments with templates."""

    self.import_file("assessment_template_no_warnings.csv")
    self.import_file("assessment_with_templates.csv")

    assessment = all_models.Assessment.query.filter(
        all_models.Assessment.slug == "A 4").first()

    values = set(v.attribute_value for v in assessment.custom_attribute_values)
    self.assertIn("abc", values)
    self.assertIn("2015-07-15", values)

  @ddt.data(
      ("T-1", {"Some Other text name*": "abc"}, set()),
      ("T-1", {"Some Other text name*": ""}, {
          errors.MISSING_VALUE_ERROR.format(
              line=3, column_name='Some Other text name'
          )
      }),
      ("", {}, set()),
  )
  @ddt.unpack
  def test_import_assmnt_with_missing_mandatory_lca(self, template,
                                                    cad, expected_errors):
    """Test importing of assessments with template and missing LCA."""

    self.import_file("assessment_template_no_warnings.csv")

    asmt_csv = OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", "A 4"),
        ("Audit", "Audit"),
        ("Template", template),
        ("Assignees", "user@example.com"),
        ("Creators", "user@example.com"),
        ("Title", "Template Assessment 1"),
        ("State", "not started"),
        ("date of birth*", "2019-06-06"),
    ])
    asmt_csv.update(cad)

    response = self.import_data(asmt_csv, dry_run=True)
    expected_messages = {
        "Assessment": {
            "row_errors": expected_errors,
        }
    }
    self._check_csv_response(response, expected_messages)

  def test_import_assessment_with_evidence_file(self):
    """Test import evidence file should add warning"""
    response = self.import_file("assessment_with_evidence_file.csv",
                                safe=False)
    evidences = all_models.Evidence.query.filter(
        all_models.Evidence.kind == all_models.Evidence.FILE).all()
    self.assertEquals(len(evidences), 0)
    expected_warning = (u"Line 11: 'Evidence File' can't be changed via "
                        u"import. Please go on Assessment page and make "
                        u"changes manually. The column will be skipped")
    expected_messages = {
        "Assessment": {
            "row_warnings": {expected_warning},
        }
    }
    self._check_csv_response(response, expected_messages)

  def test_import_assessment_with_evidence_file_existing(self):
    """If file already mapped to evidence not show warning to user"""
    evidence_url = "test_gdrive_url"

    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory()
      assessment_slug = assessment.slug
      factories.RelationshipFactory(source=audit,
                                    destination=assessment)
      evidence = factories.EvidenceFileFactory(link=evidence_url)
      factories.RelationshipFactory(source=assessment,
                                    destination=evidence)
    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", assessment_slug),
        ("Evidence File", evidence_url),
    ]))
    self.assertEquals([], response[0]['row_warnings'])

  def test_import_assessment_with_evidence_url_existing(self):
    """If url already mapped to assessment ignore it"""
    evidence_url = "test_gdrive_url"

    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory()
      assessment_slug = assessment.slug
      factories.RelationshipFactory(source=audit,
                                    destination=assessment)
      evidence = factories.EvidenceUrlFactory(link=evidence_url)
      factories.RelationshipFactory(source=assessment,
                                    destination=evidence)
    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", assessment_slug),
        ("Evidence Url", evidence_url),
    ]))

    evidences = all_models.Evidence.query.filter_by(link=evidence_url).all()
    self.assertEquals(1, len(evidences))
    self.assertEquals([], response[0]['row_warnings'])

  def test_import_assessment_with_evidence_file_multiple(self):
    """Show warning if at least one of Evidence Files not mapped"""
    evidence_url = "test_gdrive_url"

    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory()
      assessment_slug = assessment.slug
      factories.RelationshipFactory(source=audit,
                                    destination=assessment)
      evidence1 = factories.EvidenceFileFactory(link=evidence_url)
      factories.RelationshipFactory(source=assessment,
                                    destination=evidence1)
      evidence2 = factories.EvidenceFileFactory(link="test_gdrive_url_2")
      factories.RelationshipFactory(source=assessment,
                                    destination=evidence2)

    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", assessment_slug),
        ("Evidence File", evidence_url + "\n another_gdrive_url"),
    ]))
    expected_warning = (u"Line 3: 'Evidence File' can't be changed via import."
                        u" Please go on Assessment page and make changes"
                        u" manually. The column will be skipped")
    self.assertEquals([expected_warning], response[0]['row_warnings'])

  def test_import_assessment_with_evidence_file_blank_multiple(self):
    """No warnings in Evidence Files"""
    evidence_file = "test_gdrive_url \n \n another_gdrive_url"

    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory()
      assessment_slug = assessment.slug
      factories.RelationshipFactory(source=audit, destination=assessment)
      evidence1 = factories.EvidenceFileFactory(link="test_gdrive_url")
      factories.RelationshipFactory(source=assessment,
                                    destination=evidence1)
      evidence2 = factories.EvidenceFileFactory(link="another_gdrive_url")
      factories.RelationshipFactory(source=assessment,
                                    destination=evidence2)

    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", assessment_slug),
        ("Evidence File", evidence_file),
    ]))

    self.assertEquals([], response[0]['row_warnings'])

  def _test_assessment_users(self, asmt, users):
    """ Test that all users have correct roles on specified Assessment"""
    verification_errors = ""
    ac_roles = {
        acr_name: acr_id
        for acr_id, acr_name in get_custom_roles_for(asmt.type).items()
    }
    for user_name, expected_types in users.items():
      for role in expected_types:
        try:
          user = all_models.Person.query.filter_by(name=user_name).first()
          acl_len = all_models.AccessControlPerson.query.join(
              all_models.AccessControlList
          ).filter(
              all_models.AccessControlList.ac_role_id == ac_roles[role],
              all_models.AccessControlPerson.person_id == user.id,
              all_models.AccessControlList.object_id == asmt.id,
              all_models.AccessControlList.object_type == asmt.type,
          ).count()
          self.assertEqual(
              acl_len, 1,
              "User {} is not mapped to {}".format(user.email, asmt.slug)
          )
        except AssertionError as error:
          verification_errors += "\n\nChecks for Users-Assessment mapping "\
              "failed for user '{}' with:\n{}".format(user_name, str(error))

    self.assertEqual(verification_errors, "", verification_errors)

  def _test_assigned_user(self, assessment, user_id, role):
    """Check if user has role on assessment"""
    acls = all_models.AccessControlPerson.query.join(
        all_models.AccessControlList
    ).filter(
        all_models.AccessControlPerson.person_id == user_id,
        all_models.AccessControlList.object_id == assessment.id,
        all_models.AccessControlList.object_type == assessment.type,
    )
    self.assertEqual(
        [user_id] if user_id else [],
        [i.person_id for i in acls if i.ac_list.ac_role.name == role]
    )

  def test_assessment_full_no_warnings(self):
    """ Test full assessment import with no warnings

    CSV sheet:
      https://docs.google.com/spreadsheets/d/1Jg8jum2eQfvR3kZNVYbVKizWIGZXvfqv3yQpo2rIiD8/edit#gid=704933240&vpid=A7
    """
    self.import_file("assessment_full_no_warnings.csv")

    # Test first Assessment line in the CSV file
    asmt_1 = all_models.Assessment.query.filter_by(slug="Assessment 1").first()
    users = {
        "user 1": {"Assignees"},
        "user 2": {"Assignees", "Creators"}
    }
    self._test_assessment_users(asmt_1, users)
    self.assertEqual(asmt_1.status, all_models.Assessment.PROGRESS_STATE)

    # Test second Assessment line in the CSV file
    asmt_2 = all_models.Assessment.query.filter_by(slug="Assessment 2").first()
    users = {
        "user 1": {"Assignees"},
        "user 2": {"Creators"},
        "user 3": {},
        "user 4": {},
        "user 5": {},
    }
    self._test_assessment_users(asmt_2, users)
    self.assertEqual(asmt_2.status, all_models.Assessment.PROGRESS_STATE)

    audit = [obj for obj in asmt_1.related_objects() if obj.type == "Audit"][0]
    self.assertEqual(audit.context, asmt_1.context)

    evidence = all_models.Evidence.query.filter_by(
        link="http://i.imgur.com/Lppr447.jpg").first()
    self.assertEqual(audit.context, evidence.context)

  def test_assessment_import_states(self):
    """ Test Assessment state imports

    These tests are an intermediate part for zucchini release and will be
    updated in the next release.

    CSV sheet:
      https://docs.google.com/spreadsheets/d/1Jg8jum2eQfvR3kZNVYbVKizWIGZXvfqv3yQpo2rIiD8/edit#gid=299569476
    """
    self.import_file("assessment_full_no_warnings.csv")
    self.import_file("assessment_update_intermediate.csv", safe=False)

    assessments = {r.slug: r for r in all_models.Assessment.query.all()}
    self.assertEqual(assessments["Assessment 60"].status,
                     all_models.Assessment.START_STATE)
    self.assertEqual(assessments["Assessment 61"].status,
                     all_models.Assessment.PROGRESS_STATE)
    self.assertEqual(assessments["Assessment 62"].status,
                     all_models.Assessment.DONE_STATE)
    self.assertEqual(assessments["Assessment 63"].status,
                     all_models.Assessment.FINAL_STATE)
    self.assertEqual(assessments["Assessment 64"].status,
                     all_models.Assessment.FINAL_STATE)
    self.assertEqual(assessments["Assessment 3"].status,
                     all_models.Assessment.PROGRESS_STATE)
    self.assertEqual(assessments["Assessment 4"].status,
                     all_models.Assessment.PROGRESS_STATE)

    # Check that there is only one attachment left
    asmt1 = assessments["Assessment 1"]
    self.assertEqual({"a.b.com", "c d com"},
                     {i.title for i in asmt1.evidences_url})

  @unittest.skip("Test randomly fails because backend does not return errors")
  def test_error_ca_import_states(self):
    """Test changing state of Assessment with unfilled mandatory CA"""
    with factories.single_commit():
      audit = factories.AuditFactory()
      asmnt = factories.AssessmentFactory(audit=audit)
      factories.CustomAttributeDefinitionFactory(
          title="def1",
          definition_type="assessment",
          definition_id=asmnt.id,
          attribute_type="Text",
          mandatory=True,
      )
    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", asmnt.slug),
        ("Audit", audit.slug),
        ("Assignees", "user@example.com"),
        ("Creators", "user@example.com"),
        ("Title", asmnt.title),
        ("State", "Completed"),
    ]))
    expected_errors = {
        "Assessment": {
            "row_errors": {
                errors.VALIDATION_ERROR.format(
                    line=3,
                    column_name="State",
                    message="CA-introduced completion preconditions are not "
                            "satisfied. Check preconditions_failed of items "
                            "of self.custom_attribute_values"
                )
            }
        }
    }
    self._check_csv_response(response, expected_errors)
    asmnt = all_models.Assessment.query.filter(
        all_models.Assessment.slug == asmnt.slug
    ).first()
    self.assertEqual(asmnt.status, "Not Started")

  def test_assessment_warnings_errors(self):
    """ Test full assessment import with warnings and errors

    CSV sheet:
      https://docs.google.com/spreadsheets/d/1Jg8jum2eQfvR3kZNVYbVKizWIGZXvfqv3yQpo2rIiD8/edit#gid=889865936
    """
    self.import_file("assessment_full_no_warnings.csv")
    response = self.import_file("assessment_with_warnings_and_errors.csv",
                                safe=False)

    expected_errors = {
        "Assessment": {
            "block_errors": set([]),
            "block_warnings": {
                errors.UNKNOWN_COLUMN.format(
                    line=2,
                    column_name="error description - non existing column will "
                    "be ignored"
                ),
                errors.UNKNOWN_COLUMN.format(
                    line=2,
                    column_name="actual error message"
                ),
                errors.UNSUPPORTED_MAPPING.format(
                    line=2,
                    obj_a="Assessment",
                    obj_b="Project",
                    column_name="map:project"
                ),
            },
            "row_errors": {
                errors.MISSING_VALUE_ERROR.format(
                    line=19,
                    column_name="Audit"
                ),
                errors.DUPLICATE_VALUE_IN_CSV.format(
                    line="22",
                    processed_line="20",
                    column_name="Code",
                    value="Assessment 22",
                ),
            },
            "row_warnings": {
                errors.UNKNOWN_OBJECT.format(
                    line=19,
                    object_type="Audit",
                    slug="not existing"
                ),
                errors.WRONG_VALUE_DEFAULT.format(
                    line=20,
                    column_name="State",
                    value="open",
                ),
                errors.UNMODIFIABLE_COLUMN.format(
                    line=22,
                    column_name="Verified Date"
                ),
            },
        }
    }
    self._check_csv_response(response, expected_errors)

  def test_mapping_control_through_snapshot(self):
    "Test for add mapping control on assessment"
    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory(audit=audit)
      factories.RelationshipFactory(source=audit, destination=assessment)
      control = factories.ControlFactory()
    revision = all_models.Revision.query.filter(
        all_models.Revision.resource_id == control.id,
        all_models.Revision.resource_type == control.__class__.__name__
    ).order_by(
        all_models.Revision.id.desc()
    ).first()
    factories.SnapshotFactory(
        parent=audit,
        child_id=control.id,
        child_type=control.__class__.__name__,
        revision_id=revision.id
    )
    db.session.commit()
    self.assertFalse(db.session.query(
        all_models.Relationship.get_related_query(
            assessment, all_models.Snapshot()
        ).exists()).first()[0])
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", assessment.slug),
        ("map:Control versions", control.slug),
    ]))
    self.assertTrue(db.session.query(
        all_models.Relationship.get_related_query(
            assessment, all_models.Snapshot()
        ).exists()).first()[0])

  @ddt.data(
      ("yes", True),
      ("no", True),
      ("invalid_data", False),
  )
  @ddt.unpack
  def test_import_view_only_field(self, value, is_valid):
    "Test import view only fields"
    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory(audit=audit)
      factories.RelationshipFactory(source=audit, destination=assessment)
    resp = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", assessment.slug),
        ("archived", value),
    ]))
    row_warnings = []
    if not is_valid:
      row_warnings.append(u"Line 3: Field 'Archived' contains invalid data. "
                          u"The value will be ignored.")
    self.assertEqual(
        [{
            u'ignored': 0,
            u'updated': 1,
            u'block_errors': [],
            u'name': u'Assessment',
            u'created': 0,
            u'deleted': 0,
            u'deprecated': 0,
            u'row_warnings': row_warnings,
            u'rows': 1,
            u'block_warnings': [],
            u'row_errors': [],
        }],
        resp)

  @ddt.data((False, "no", 0, 1, []),
            (True, "yes", 1, 0, [u'Line 3: Importing archived instance is '
                                 u'prohibited. The line will be ignored.']))
  @ddt.unpack
  # pylint: disable=too-many-arguments
  def test_import_archived_assessment(self, is_archived, value, ignored,
                                      updated, row_errors):
    """Test archived assessment import procedure"""
    with factories.single_commit():
      audit = factories.AuditFactory(archived=is_archived)
      assessment = factories.AssessmentFactory(audit=audit)
      factories.RelationshipFactory(source=audit, destination=assessment)
    resp = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", assessment.slug),
        ("archived", value),
        ("description", "archived assessment description")
    ]))
    self.assertEqual([{
        u'ignored': ignored,
        u'updated': updated,
        u'block_errors': [],
        u'name': u'Assessment',
        u'created': 0,
        u'deleted': 0,
        u'deprecated': 0,
        u'row_warnings': [],
        u'rows': 1,
        u'block_warnings': [],
        u'row_errors': row_errors
    }], resp)

  def test_create_new_assessment_with_mapped_control(self):
    "Test for creation assessment with mapped controls"
    with factories.single_commit():
      audit = factories.AuditFactory()
      control = factories.ControlFactory()
    revision = all_models.Revision.query.filter(
        all_models.Revision.resource_id == control.id,
        all_models.Revision.resource_type == control.__class__.__name__
    ).order_by(
        all_models.Revision.id.desc()
    ).first()
    factories.SnapshotFactory(
        parent=audit,
        child_id=control.id,
        child_type=control.__class__.__name__,
        revision_id=revision.id
    )
    db.session.commit()
    self.assertFalse(db.session.query(
        all_models.Relationship.get_related_query(
            all_models.Assessment(), all_models.Snapshot()
        ).exists()).first()[0])
    slug = "TestAssessment"
    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Audit*", audit.slug),
        ("Assignees*", all_models.Person.query.all()[0].email),
        ("Creators", all_models.Person.query.all()[0].email),
        ("Title", "Strange title"),
        ("map:Control versions", control.slug),
    ]))
    self._check_csv_response(response, {})
    assessment = all_models.Assessment.query.filter(
        all_models.Assessment.slug == slug
    ).first()
    self.assertTrue(db.session.query(all_models.Relationship.get_related_query(
        assessment, all_models.Snapshot()).exists()).first()[0]
    )

  def test_create_import_assignee(self):
    "Test for creation assessment with mapped assignees"
    name = "test_name"
    email = "test@email.com"
    slug = "TestAssessment"
    with factories.single_commit():
      audit = factories.AuditFactory()
      assignee_id = factories.PersonFactory(name=name, email=email).id
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Audit*", audit.slug),
        ("Assignees*", email),
        ("Creators", all_models.Person.query.all()[0].email),
        ("Title", "Strange title"),
    ]))
    assessment = all_models.Assessment.query.filter(
        all_models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, assignee_id, "Assignees")

  def test_create_import_creators(self):
    "Test for creation assessment with mapped creator"
    name = "test_name"
    email = "test@email.com"
    slug = "TestAssessment"
    with factories.single_commit():
      audit = factories.AuditFactory()
      creator_id = factories.PersonFactory(name=name, email=email).id
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Audit*", audit.slug),
        ("Assignees*", all_models.Person.query.all()[0].email),
        ("Creators", email),
        ("Title", "Strange title"),
    ]))
    assessment = all_models.Assessment.query.filter(
        all_models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, creator_id, "Creators")

  def test_update_import_creators(self):
    "Test for creation assessment with mapped creator"
    slug = "TestAssessment"
    name = "test_name"
    email = "test@email.com"
    with factories.single_commit():
      assessment = factories.AssessmentFactory(slug=slug)
      creator_id = factories.PersonFactory(name=name, email=email).id
    self._test_assigned_user(assessment, None, "Creators")
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Creators", email),
    ]))
    assessment = all_models.Assessment.query.filter(
        all_models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, creator_id, "Creators")

  def test_update_import_assignee(self):
    "Test for creation assessment with mapped creator"
    slug = "TestAssessment"
    name = "test_name"
    email = "test@email.com"
    with factories.single_commit():
      assessment = factories.AssessmentFactory(slug=slug)
      assignee_id = factories.PersonFactory(name=name, email=email).id
    self._test_assigned_user(assessment, None, "Assignees")
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Assignees", email),
    ]))
    assessment = all_models.Assessment.query.filter(
        all_models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, assignee_id, "Assignees")

  def test_update_import_verifiers(self):
    """Test import does not delete verifiers if empty value imported"""
    slug = "TestAssessment"
    assessment = factories.AssessmentFactory(slug=slug)

    name = "test_name"
    email = "test@email.com"
    verifier = factories.PersonFactory(name=name, email=email)
    verifier_id = verifier.id

    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Verifiers", email),
    ]))
    assessment = all_models.Assessment.query.filter(
        all_models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, verifier_id, "Verifiers")
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", slug),
        ("Verifiers", ""),
    ]))
    assessment = all_models.Assessment.query.filter(
        all_models.Assessment.slug == slug
    ).first()
    self._test_assigned_user(assessment, verifier_id, "Verifiers")

  @ddt.data(
      (
          "Created Date",
          lambda: datetime.date.today() - datetime.timedelta(7),
      ),
  )
  @ddt.unpack
  def test_update_non_changeable_field(self, field, value_creator):
    """Test importing Assessment's "Created Date" field"""
    slug = "TestAssessment"
    with factories.single_commit():
      value = value_creator()
      factories.AssessmentFactory(
          slug=slug,
          modified_by=factories.PersonFactory(email="modifier@email.com"),
      )
    data = [{
        "object_name": "Assessment",
        "fields": "all",
        "filters": {
            "expression": {
                "left": "code",
                "op": {"name": "="},
                "right": slug
            },
        }
    }]
    before_update = self.export_parsed_csv(data)["Assessment"][0][field]
    with freezegun.freeze_time("2017-9-10"):
      self.import_data(OrderedDict([("object_type", "Assessment"),
                                    ("Code*", slug),
                                    (field, value)]))
    self.assertEqual(before_update,
                     self.export_parsed_csv(data)["Assessment"][0][field])

  @ddt.data(
      ("Last Updated By", "new_user@email.com"),
  )
  @ddt.unpack
  def test_exportable_only_updated_by(self, field, value):
    """Test exportable only "Last Updated By" field"""
    slug = "TestAssessment"
    with factories.single_commit():
      factories.AssessmentFactory(
          slug=slug,
          modified_by=factories.PersonFactory(email="modifier@email.com"),
      )
    data = [{
        "object_name": "Assessment",
        "fields": "all",
        "filters": {
            "expression": {
                "left": "code",
                "op": {"name": "="},
                "right": slug
            },
        }
    }]
    before_update = self.export_parsed_csv(data)["Assessment"][0][field]
    self.assertEqual(before_update, "modifier@email.com")
    self.import_data(OrderedDict([("object_type", "Assessment"),
                                  ("Code*", slug),
                                  (field, value)]))
    after_update = self.export_parsed_csv(data)["Assessment"][0][field]
    self.assertEqual(after_update, "user@example.com")

  def test_import_last_deprecated_date(self):
    """Last Deprecated Date on assessment should be non editable."""
    with factories.single_commit():
      with freezegun.freeze_time("2017-01-01"):
        assessment = factories.AssessmentFactory(status="Deprecated")

    resp = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("code", assessment.slug),
        ("Last Deprecated Date", "02/02/2017"),
    ]))

    result = all_models.Assessment.query.get(assessment.id)

    self.assertEqual(1, len(resp))
    self.assertEqual(1, resp[0]["updated"])
    self.assertEqual(result.end_date, datetime.date(2017, 1, 1))

  @ddt.data(*all_models.Assessment.VALID_STATES)
  def test_import_set_up_deprecated(self, start_state):
    """Update assessment from {0} to Deprecated."""
    with factories.single_commit():
      assessment = factories.AssessmentFactory(status=start_state)
    resp = self.import_data(
        OrderedDict([
            ("object_type", "Assessment"),
            ("code", assessment.slug),
            ("State", all_models.Assessment.DEPRECATED),
        ]))
    self.assertEqual(1, len(resp))

    self.assertEqual(1, resp[0]["updated"])
    self.assertEqual(
        all_models.Assessment.query.get(assessment.id).status,
        all_models.Assessment.DEPRECATED)

  def test_asmnt_cads_update_completed(self):
    """Test update of assessment without cads."""
    with factories.single_commit():
      audit = factories.AuditFactory()
      asmnt = factories.AssessmentFactory(audit=audit)
      factories.CustomAttributeDefinitionFactory(
          title="CAD",
          definition_type="assessment",
          definition_id=asmnt.id,
          attribute_type="Text",
          mandatory=True,
      )
    data = OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", asmnt.slug),
        ("Audit", audit.slug),
        ("Title", "Test title"),
        ("State", "Completed"),
        ("CAD", "Some value"),
    ])
    response = self.import_data(data)
    self._check_csv_response(response, {})

  def test_import_asmnt_rev_query_count(self):
    """Test only one revisions insert query should occur while importing."""
    with factories.single_commit():
      audit = factories.AuditFactory()
      asmnt = factories.AssessmentFactory(audit=audit)
      cad_names = ("CAD1", "CAD2", "CAD3")
      for name in cad_names:
        factories.CustomAttributeDefinitionFactory(
            title=name,
            definition_type="assessment",
            definition_id=asmnt.id,
            attribute_type="Text",
            mandatory=True,
        )
    data = OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", asmnt.slug),
        ("Audit", audit.slug),
        ("Title", "Test title"),
        ("State", "Completed"),
        ("CAD1", "Some value 1"),
        ("CAD2", "Some value 2"),
        ("CAD3", "Some value 3"),
    ])
    with utils.QueryCounter() as counter:
      response = self.import_data(data)
    self._check_csv_response(response, {})
    rev_insert_queries = [query for query in counter.queries
                          if 'INSERT INTO revisions' in query]
    self.assertEqual(len(rev_insert_queries), 1)

  @ddt.data(
      ("", "In Review", "", True),
      ("", "In Review", "user@example.com", False),
      ("", "Rework Needed", "", True),
      ("12/27/2018", "Completed", "", True),
      ("", "Completed", "", False),
      ("12/27/2018", "Completed", "user@example.com", False),
      ("", "In Progress", "", False),
  )
  @ddt.unpack
  def test_asmt_status_and_verifier(self, date, status, verifiers, warning):
    """Test assessment status validation requiring verifier"""
    audit = factories.AuditFactory()
    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code*", ""),
        ("Title", "Test title"),
        ("Audit", audit.slug),
        ("Creators", "user@example.com"),
        ("Assignees", "user@example.com"),
        ("Verifiers", verifiers),
        ("Verified Date", date),
        ("State", status),
    ]))
    expected_warnings = {
        'Assessment': {
            'row_warnings': {
                errors.NO_VERIFIER_WARNING.format(
                    line=3,
                    status=status
                )}}}
    if warning:
      self._check_csv_response(response, expected_warnings)
    else:
      self._check_csv_response(response, {})

  def test_asmt_verified_date_update_from_none(self):
    """Test that we able to set Verified Date if it is empty"""
    audit = factories.AuditFactory()
    assessment = factories.AssessmentFactory(audit=audit)
    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code", assessment.slug),
        ("Verifiers", "user@example.com"),
        ("Verified Date", "01/22/2019"),
    ]))
    self._check_csv_response(response, {})
    self.assertEqual(
        all_models.Assessment.query.get(assessment.id).verified_date,
        datetime.datetime(2019, 1, 22))

  def test_asmt_verified_date_readonly(self):
    """Test that Verified Date is readonly"""
    audit = factories.AuditFactory()
    date = datetime.datetime(2019, 05, 22)
    assessment = \
        factories.AssessmentFactory(audit=audit,
                                    verified_date=date)
    expected_warnings = {
        'Assessment': {
            'row_warnings': {
                errors.UNMODIFIABLE_COLUMN.format(
                    line=3,
                    column_name="Verified Date"
                )}}}
    response = self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code", assessment.slug),
        ("Verifiers", "user@example.com"),
        ("Verified Date", "01/21/2019"),
    ]))
    self._check_csv_response(response, expected_warnings)
    self.assertEqual(
        all_models.Assessment.query.get(assessment.id).verified_date,
        date)

  @ddt.data("user@example.com", "--")
  def test_asmt_state_after_updating_verifiers(self, new_verifier):
    """Test that after updating Verifiers assessment became In Progress"""
    audit = factories.AuditFactory()
    assessment = \
        factories.AssessmentFactory(audit=audit,
                                    status=all_models.Assessment.DONE_STATE,
                                    )
    person = factories.PersonFactory(email="verifier@example.com")
    factories.AccessControlPersonFactory(
        ac_list=assessment.acr_name_acl_map["Verifiers"],
        person=person,
    )
    self.assertEqual(
        all_models.Assessment.query.get(assessment.id).status,
        all_models.Assessment.DONE_STATE)
    self.import_data(OrderedDict([
        ("object_type", "Assessment"),
        ("Code", assessment.slug),
        ("Verifiers", new_verifier),
    ]))
    self.assertEqual(
        all_models.Assessment.query.get(assessment.id).status,
        all_models.Assessment.PROGRESS_STATE)


@ddt.ddt
class TestAssessmentExport(TestCase):
  """Test Assessment object export."""

  def setUp(self):
    """ Set up for Assessment test cases """
    super(TestAssessmentExport, self).setUp()
    self.client.get("/login")
    self.headers = ObjectGenerator.get_header()

  def test_simple_export(self):
    """ Test full assessment export with no warnings"""
    self.import_file("assessment_full_no_warnings.csv")
    data = [{
        "object_name": "Assessment",
        "filters": {
            "expression": {}
        },
        "fields": "all",
    }]
    response = self.export_csv(data)
    # check that Assessment 1 -> description utf8 exported properly
    self.assertIn(u"\u5555", response.data.decode("utf8"))

  def assertColumnExportedValue(self, value, instance, column):
    """ Assertion checks is value equal to exported instance column value."""
    data = [{
        "object_name": instance.__class__.__name__,
        "fields": "all",
        "filters": {
            "expression": {
                "text": str(instance.id),
                "op": {
                    "name": "text_search",
                }
            },
        },
    }]
    instance_dict = self.export_parsed_csv(data)[instance.type][0]
    self.assertEqual(value, instance_dict[column])

  def test_export_assesments_without_map_control(self):
    """Test export assesment without related control instance"""
    audit = factories.AuditFactory()
    assessment = factories.AssessmentFactory(audit=audit)
    factories.RelationshipFactory(source=audit, destination=assessment)
    control = factories.ControlFactory()
    revision = all_models.Revision.query.filter(
        all_models.Revision.resource_id == control.id,
        all_models.Revision.resource_type == control.__class__.__name__
    ).order_by(
        all_models.Revision.id.desc()
    ).first()
    factories.SnapshotFactory(
        parent=audit,
        child_id=control.id,
        child_type=control.__class__.__name__,
        revision_id=revision.id
    )
    db.session.commit()
    self.assertColumnExportedValue("", assessment,
                                   "map:control versions")

  @ddt.data(True, False)
  def test_export_assesments_map_control(self, with_map):
    """Test export assesment with and without related control instance"""
    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory(audit=audit)
      factories.RelationshipFactory(source=audit, destination=assessment)
      control = factories.ControlFactory()
    revision = all_models.Revision.query.filter(
        all_models.Revision.resource_id == control.id,
        all_models.Revision.resource_type == control.__class__.__name__
    ).order_by(
        all_models.Revision.id.desc()
    ).first()
    with factories.single_commit():
      snapshot = factories.SnapshotFactory(
          parent=audit,
          child_id=control.id,
          child_type=control.__class__.__name__,
          revision_id=revision.id
      )
      if with_map:
        factories.RelationshipFactory(source=snapshot, destination=assessment)
    if with_map:
      val = control.slug
    else:
      val = ""
    self.assertColumnExportedValue(val, assessment,
                                   "map:control versions")

  def test_export_assesments_with_map_control_mirror_relation(self):
    """Test export assesment with related control instance

    relation assessment -> snapshot
    """
    with factories.single_commit():
      audit = factories.AuditFactory()
      assessment = factories.AssessmentFactory(audit=audit)
      factories.RelationshipFactory(source=audit, destination=assessment)
      control = factories.ControlFactory()
    revision = all_models.Revision.query.filter(
        all_models.Revision.resource_id == control.id,
        all_models.Revision.resource_type == control.__class__.__name__
    ).order_by(
        all_models.Revision.id.desc()
    ).first()
    snapshot = factories.SnapshotFactory(
        parent=audit,
        child_id=control.id,
        child_type=control.__class__.__name__,
        revision_id=revision.id
    )
    db.session.commit()
    factories.RelationshipFactory(destination=snapshot, source=assessment)
    self.assertColumnExportedValue(control.slug, assessment,
                                   "map:control versions")

  def test_export_assessments_with_filters_and_conflicting_ca_names(self):
    """Test exporting assessments with conflicting custom attribute names."""
    self.import_file("assessment_template_no_warnings.csv")
    self.import_file("assessment_with_templates.csv")

    # also create an object level custom attribute with a name that clashes
    # with a name of a "regular" attribute
    assessment = all_models.Assessment.query.filter(
        all_models.Assessment.slug == u"A 2").first()
    cad = all_models.CustomAttributeDefinition(
        attribute_type=u"Text",
        title=u"ca title",
        definition_type=u"assessment",
        definition_id=assessment.id
    )
    db.session.add(cad)
    db.session.commit()

    data = [{
        "object_name": "Assessment",
        "fields": ["slug", "title", "description", "status"],
        "filters": {
            "expression": {
                "left": {
                    "left": "code",
                    "op": {"name": "~"},
                    "right": "A 2"
                },
                "op": {"name": "AND"},
                "right": {
                    "left": "title",
                    "op": {"name": "~"},
                    "right": "no template Assessment"
                }
            },
            "keys": ["code", "title", "status"],
            "order_by": {
                "keys": [],
                "order": "",
                "compare": None
            }
        }
    }]

    response = self.export_csv(data)
    self.assertIn(u"No template Assessment 2", response.data)

  @ddt.data(
      ("Last Updated By", "new_user@email.com"),
      ("modified_by", "new_user1@email.com"),
  )
  @ddt.unpack
  def test_export_by_modified_by(self, field, email):
    """Test for creation assessment with mapped creator"""
    slug = "TestAssessment"
    with factories.single_commit():
      factories.AssessmentFactory(
          slug=slug,
          modified_by=factories.PersonFactory(email=email),
      )
    data = [{
        "object_name": "Assessment",
        "fields": "all",
        "filters": {
            "expression": {
                "left": field,
                "op": {"name": "="},
                "right": email
            },
        }
    }]

    resp = self.export_parsed_csv(data)["Assessment"]
    self.assertEqual(1, len(resp))
    self.assertEqual(slug, resp[0]["Code*"])
