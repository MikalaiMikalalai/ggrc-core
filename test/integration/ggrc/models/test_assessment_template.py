# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Tests for AssessmentTemplate model."""
from ggrc.integrations import constants
from ggrc.models import all_models

from integration.ggrc import TestCase, Api
from integration.ggrc.models import factories


class TestAssessmentTemplate(TestCase):
  """ Test AssessmentTemplate class. """
  def setUp(self):
    super(TestAssessmentTemplate, self).setUp()
    self.api = Api()

  def test_audit_setup(self):
    """Test audit setup for assessment_template"""
    audit = factories.AuditFactory()
    response = self.api.post(all_models.AssessmentTemplate, {
        "assessment_template": {
            "audit": {"id": audit.id},
            "context": {"id": audit.context.id},
            "default_people": {
                "assignees": "Admin",
                "verifiers": "Admin",
            },
            "title": "Some title"
        }
    })
    self.assertStatus(response, 201)
    template_id = response.json["assessment_template"]["id"]
    template = all_models.AssessmentTemplate.query.get(template_id)
    self.assertEqual(template.audit.id, audit.id)

  def test_audit_issue_tracker(self):
    """Test existing audit issue_tracker info in template response"""
    with factories.single_commit():
      audit = factories.AuditFactory()
      audit_id = audit.id
      factories.IssueTrackerIssueFactory(
          issue_tracked_obj=audit,
          component_id="some component id",
          hotlist_id="some host id",
          title="some title",
          issue_id="some issue id"
      )
      template_id = factories.AssessmentTemplateFactory(
          audit=audit,
          context=audit.context
      ).id
    response = self.api.get(all_models.AssessmentTemplate, template_id)
    self.assert200(response)
    audit = all_models.Audit.query.get(audit_id)
    default_issue_type = constants.DEFAULT_ISSUETRACKER_VALUES['issue_type']
    self.assertEqual(
        response.json["assessment_template"]["audit"],
        {
            u"type": u"Audit",
            u"id": long(audit.id),
            u'title': unicode(audit.title),
            u"href": u"/api/audits/{}".format(long(audit.id)),
            u"context_id": long(audit.context.id),
            u"issue_tracker": {
                u'_warnings': [],
                u"component_id": u"some component id",
                u"enabled": False,
                u"issue_severity": None,
                u"hotlist_id": u"some host id",
                u"issue_id": u"some issue id",
                u"issue_priority": None,
                u"issue_type": default_issue_type,
                u"issue_url": None,
                u"title": "some title"
            }
        }
    )
