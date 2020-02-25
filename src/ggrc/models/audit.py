# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Audit model."""

from sqlalchemy import orm
from werkzeug import exceptions as wzg_exceptions

from ggrc import db
from ggrc.access_control.roleable import Roleable
from ggrc.builder import simple_property
from ggrc.fulltext.mixin import Indexed
from ggrc.login import get_current_user
from ggrc.models import mixins
from ggrc.models import reflection
from ggrc.models.context import HasOwnContext
from ggrc.models.deferred import deferred
from ggrc.models.evidence import Evidence
from ggrc.models.mixins import base
from ggrc.models.mixins import clonable
from ggrc.models.mixins import WithLastDeprecatedDate
from ggrc.models.mixins import issue_tracker as issue_tracker_mixins
from ggrc.models.mixins import rest_handable as rest_handable_mixins
from ggrc.models.mixins.with_evidence import WithEvidence
from ggrc.models.object_person import Personable
from ggrc.models.program import Program
from ggrc.models.relationship import Relatable, Relationship
from ggrc.models.snapshot import Snapshotable
from ggrc.rbac import SystemWideRoles
from ggrc.utils import errors
from ggrc.integrations import constants
from ggrc.fulltext import attributes


class Audit(Snapshotable,
            clonable.SingleClonable,
            WithEvidence,
            mixins.CustomAttributable,
            Personable,
            HasOwnContext,
            Relatable,
            Roleable,
            issue_tracker_mixins.IssueTrackedWithConfig,
            issue_tracker_mixins.IssueTrackedWithPeopleSync,
            WithLastDeprecatedDate,
            mixins.Timeboxed,
            base.ContextRBAC,
            mixins.BusinessObject,
            mixins.Folderable,
            rest_handable_mixins.WithDeleteHandable,
            Indexed,
            db.Model):
  """Audit model."""

  __tablename__ = 'audits'
  _slug_uniqueness = False

  VALID_STATES = (
      u'Planned', u'In Progress', u'Manager Review',
      u'Ready for External Review', u'Completed', u'Deprecated'
  )

  CLONEABLE_CHILDREN = {"AssessmentTemplate"}

  report_start_date = deferred(db.Column(db.Date), 'Audit')
  report_end_date = deferred(db.Column(db.Date), 'Audit')
  audit_firm_id = deferred(
      db.Column(db.Integer, db.ForeignKey('org_groups.id')), 'Audit')
  audit_firm = db.relationship('OrgGroup', uselist=False)
  gdrive_evidence_folder = deferred(db.Column(db.String), 'Audit')
  program_id = deferred(
      db.Column(db.Integer, db.ForeignKey('programs.id'), nullable=False),
      'Audit')
  object_type = db.Column(
      db.String(length=250), nullable=False, default='Control')

  assessments = db.relationship('Assessment', backref='audit')
  issues = db.relationship('Issue', backref='audit')
  snapshots = db.relationship('Snapshot', backref='audit')
  archived = deferred(db.Column(db.Boolean,
                                nullable=False, default=False), 'Audit')
  manual_snapshots = deferred(db.Column(db.Boolean,
                              nullable=False, default=False), 'Audit')
  assessment_templates = db.relationship('AssessmentTemplate', backref='audit')

  _api_attrs = reflection.ApiAttributes(
      'report_start_date',
      'report_end_date',
      'audit_firm',
      'gdrive_evidence_folder',
      'program',
      'object_type',
      'archived',
      'manual_snapshots',
  )

  _fulltext_attrs = [
      attributes.BooleanFullTextAttr(
          'archived',
          'archived',
          true_value="Yes",
          false_value="No",
      ),
      'report_start_date',
      'report_end_date',
      'audit_firm',
      'gdrive_evidence_folder',
  ]

  @classmethod
  def indexed_query(cls):
    return super(Audit, cls).indexed_query().options(
        orm.Load(cls).undefer_group(
            "Audit_complete",
        ),
    )

  _sanitize_html = [
      'gdrive_evidence_folder',
      'description',
  ]

  _include_links = []

  _aliases = {
      "program": {
          "display_name": "Program",
          "filter_by": "_filter_by_program",
          "mandatory": True,
      },
      "start_date": "Planned Start Date",
      "end_date": "Planned End Date",
      "report_start_date": "Planned Report Period from",
      "report_end_date": "Planned Report Period to",
      "notes": None,
      "archived": {
          "display_name": "Archived",
          "mandatory": False,
          "description": "Allowed values are:\nyes\nno"
      },
      "status": {
          "display_name": "State",
          "mandatory": True,
          "description": "Allowed values are:\n{}".format(
              '\n'.join(VALID_STATES))
      },
      "issue_priority": {
          "display_name": "Priority",
          "mandatory": False,
          "description": "Allowed values are:\n{}".format(
              '\n'.join(constants.AVAILABLE_PRIORITIES)),
      },
  }

  def _clone(self, source_object):
    """Clone audit and all relevant attributes.

    Keeps the internals of actual audit cloning and everything that is related
    to audit itself (auditors, audit firm, context setting,
    custom attribute values, etc.)
    """

    # NOTE. Currently this function is called from Restful.collection_posted
    # hook. The following operations are performed:
    # 1) create new object, call json_create(), where attributes will be set
    #    with value validation
    # 2) current function is called from(Restful.collection_posted
    #    which overrides some attributes, attribute validator for these
    #    attributes are called
    # So, validation for those attrs are called twice!
    # One corner case of this behavior is validation of field "title".
    # title cannot be None, and because title validation is performed before
    # this function, API request MUST contain non-empty title in dict,
    # however the value will be overridden and re-validated in this function!

    from ggrc_basic_permissions import create_audit_context
    data = {
        "title": source_object.generate_attribute("title"),
        "description": source_object.description,
        "audit_firm": source_object.audit_firm,
        "start_date": source_object.start_date,
        "end_date": source_object.end_date,
        "last_deprecated_date": source_object.last_deprecated_date,
        "program": source_object.program,
        "status": source_object.VALID_STATES[0],
        "report_start_date": source_object.report_start_date,
        "report_end_date": source_object.report_end_date
    }

    self.update_attrs(data)
    db.session.flush()

    create_audit_context(self)
    self.clone_acls(source_object)
    self.clone_custom_attribute_values(source_object)

  def clone_acls(self, audit):
    """Clone acl roles like auditors and audit captains

    Args:
      audit: Audit instance
    """
    for person, acl in audit.access_control_list:
      self.add_person_with_role(person, acl.ac_role)

  def clone(self, source_id, mapped_objects=None):
    """Clone audit with specified whitelisted children.

    Children that can be cloned should be specified in CLONEABLE_CHILDREN.

    Args:
      mapped_objects: A list of related objects that should also be copied and
      linked to a new audit.
    """
    if not mapped_objects:
      mapped_objects = []

    source_object = Audit.query.get(source_id)
    self._clone(source_object)

    if any(mapped_objects):
      related_children = source_object.related_objects(mapped_objects)

      for obj in related_children:
        obj.clone(self)

  @orm.validates("archived")
  def archived_check(self, _, value):
    """Only Admins and Program Managers are allowed to (un)archive Audit."""
    user = get_current_user()
    if getattr(user, 'system_wide_role', None) in SystemWideRoles.admins:
      return value

    if self.archived is not None and self.archived != value and \
       not any(acl for person, acl in list(self.program.access_control_list)
               if acl.ac_role.name == "Program Managers" and
               person.id == user.id):
      raise wzg_exceptions.Forbidden()
    return value

  @classmethod
  def _filter_by_program(cls, predicate):
    """Helper for filtering by program"""
    return Program.query.filter(
        (Program.id == Audit.program_id) &
        (predicate(Program.slug) | predicate(Program.title))
    ).exists()

  @classmethod
  def eager_query(cls, **kwargs):
    """Eager Query."""
    query = super(Audit, cls).eager_query(**kwargs)
    options = {
        'program': orm.joinedload('program'),
        'object_people': orm.subqueryload('object_people')
                            .joinedload('person'),
    }
    return cls.populate_query(query, options, **kwargs)

  def get_evidences_from_assessments(self, objects=False):
    """Return all related evidences from assessments.
      audit <--> assessment -> evidence

    :param objects: bool. optional argument.
          If True object Evidence ORM objects return
    :return: sqlalchemy.Query or sqlalchemy.orm.query.Query objects
    """
    from ggrc.models.assessment import Assessment
    evid_as_dest = db.session.query(
        Relationship.destination_id.label("id"),
    ).join(
        Assessment,
        Assessment.id == Relationship.source_id,
    ).filter(
        Relationship.destination_type == Evidence.__name__,
        Relationship.source_type == Assessment.__name__,
        Assessment.audit_id == self.id,
    )
    evid_as_source = db.session.query(
        Relationship.source_id.label("id"),
    ).join(
        Assessment,
        Assessment.id == Relationship.destination_id,
    ).filter(
        Relationship.source_type == Evidence.__name__,
        Relationship.destination_type == Assessment.__name__,
        Assessment.audit_id == self.id,
    )
    evidence_assessment = evid_as_dest.union(evid_as_source)
    if objects:
      return db.session.query(Evidence).filter(
          Evidence.id.in_(evidence_assessment),
      )
    return evidence_assessment

  def get_evidences_from_audit(self, objects=False):
    """Return all related evidence. In relation audit <--> evidence

    :param objects: bool. optional argument.
          If True object Evidence ORM objects return
    :return: sqlalchemy.Query or sqlalchemy.orm.query.Query objects
    """

    evid_a_source = db.session.query(
        Relationship.source_id.label("id"),
    ).filter(
        Relationship.source_type == Evidence.__name__,
        Relationship.destination_type == Audit.__name__,
        Relationship.destination_id == self.id,
    )
    evid_a_dest = db.session.query(
        Relationship.destination_id.label("id"),
    ).filter(
        Relationship.destination_type == Evidence.__name__,
        Relationship.source_type == Audit.__name__,
        Relationship.source_id == self.id,
    )
    evidence_audit = evid_a_dest.union(evid_a_source)
    if objects:
      return db.session.query(Evidence).filter(
          Evidence.id.in_(evidence_audit),
      )
    return evidence_audit

  @simple_property
  def all_related_evidences(self):
    """Return all related evidences of audit"""
    evidence_assessment = self.get_evidences_from_assessments()
    evidence_audit = self.get_evidences_from_audit()
    evidence_ids = evidence_assessment.union(evidence_audit)
    return db.session.query(Evidence).filter(
        Evidence.id.in_(evidence_ids)
    )

  def _check_no_assessments(self):
    """Check that audit has no assessments before delete."""
    if self.assessments or self.assessment_templates:
      db.session.rollback()
      raise wzg_exceptions.Conflict(errors.MAPPED_ASSESSMENT)

  def handle_delete(self):
    """Handle model_deleted signals."""
    self._check_no_assessments()


def build_audit_stub(obj):
  """Returns a stub of audit model to which assessment is related to."""
  audit_id = obj.audit_id
  if audit_id is None:
    return None
  return {
      'type': 'Audit',
      'id': audit_id,
      'title': obj.audit.title,
      'context_id': obj.context_id,
      'href': '/api/audits/%d' % audit_id,
      'issue_tracker': obj.audit.issue_tracker,
  }
