# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Module for Snapshot object"""

from sqlalchemy import event
from sqlalchemy import func
from sqlalchemy import inspect
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm.session import Session
from sqlalchemy.sql.expression import tuple_, and_, or_
from werkzeug import exceptions

from ggrc import builder
from ggrc import db
from ggrc.access_control import roleable
from ggrc.models import inflector
from ggrc.models import mixins
from ggrc.models import reflection
from ggrc.models import relationship
from ggrc.models import revision
from ggrc.models.mixins import base
from ggrc.models.mixins import rest_handable
from ggrc.models.mixins import with_last_assessment_date
from ggrc.models.mixins.synchronizable import Synchronizable
from ggrc.utils import benchmark
from ggrc.utils import errors
from ggrc.utils import referenced_objects
from ggrc.utils.revisions_diff import builder as revisions_diff


class Snapshot(rest_handable.WithDeleteHandable,
               roleable.Roleable,
               relationship.Relatable,
               with_last_assessment_date.WithLastAssessmentDate,
               base.ContextRBAC,
               mixins.Base,
               db.Model):
  """Snapshot object that holds a join of parent object, revision, child object
  and parent object's context.

  Conceptual model is that we have a parent snapshotable object (e.g. Audit)
  which will not create relationships to objects with automapper at the time of
  creation but will instead create snapshots of those objects based on the
  latest revision of the object at the time of create / update of the object.
  Objects that were supposed to be mapped are called child objects.
  """
  __tablename__ = "snapshots"

  _api_attrs = reflection.ApiAttributes(
      "parent",
      "child_id",
      "child_type",
      reflection.Attribute("revision", create=False, update=False),
      reflection.Attribute("revision_id", create=False, update=False),
      reflection.Attribute("archived", create=False, update=False),
      reflection.Attribute("revisions", create=False, update=False),
      reflection.Attribute("is_latest_revision", create=False, update=False),
      reflection.Attribute("original_object_deleted",
                           create=False,
                           update=False),
      reflection.Attribute("is_identical_revision", create=False,
                           update=False),
      reflection.Attribute("update_revision", read=False),
  )

  _include_links = [
      "revision"
  ]
  _aliases = {
      "attributes": "Attributes",
      "archived": "Archived",
      "mappings": {
          "display_name": "Mappings",
          "type": "mapping",
      }
  }

  parent_id = db.Column(
      db.Integer,
      db.ForeignKey("audits.id", ondelete='CASCADE'),
      nullable=False,
  )
  parent_type = db.Column(db.String, nullable=False, default="Audit")

  @orm.validates("parent_type")
  def validate_parent_type(self, _, value):
    """Validates parent_type equals 'Audit'"""
    # pylint: disable=no-self-use
    if value != "Audit":
      raise ValueError("Wrong 'parent_type' value. Only 'Audit' supported")
    return value

  # Child ID and child type are data denormalisations - we could easily get
  # them from revision.content, but since that is a JSON field it will be
  # easier for development to just denormalise on write and not worry
  # about it.
  child_id = db.Column(db.Integer, nullable=False)
  child_type = db.Column(db.String, nullable=False)

  revision_id = db.Column(
      db.Integer,
      db.ForeignKey("revisions.id"),
      nullable=False
  )

  revision = db.relationship(
      "Revision",
      lazy="joined",
  )

  _update_revision = None

  revisions = db.relationship(
      "Revision",
      primaryjoin="and_(Revision.resource_id == foreign(Snapshot.child_id),"
      "Revision.resource_type == foreign(Snapshot.child_type))",
      uselist=True,
  )

  @builder.simple_property
  def archived(self):
    return self.audit.archived if self.audit else False

  @builder.simple_property
  def is_latest_revision(self):
    """Flag if the snapshot has the latest revision."""
    return self.revisions and self.revision == self.revisions[-1]

  @builder.simple_property
  def original_object_deleted(self):
    """Flag if the snapshot has the last revision and action is deleted."""
    if not self.revisions:
      return False
    deleted = self.revisions[-1].action == "deleted"
    external_deleted = (
        self.revisions[-1].content["status"] == "Deprecated" and
        issubclass(inflector.get_model(self.child_type), Synchronizable)
    )
    return bool(deleted or external_deleted)

  @builder.simple_property
  def is_identical_revision(self):
    """Flag if the snapshot has the identical revision."""
    instance = referenced_objects.get(self.child_type, self.child_id)
    return self.revisions and revisions_diff.is_identical_revision(
        instance,
        self.revision.content,
        self.revisions[-1].content
    )

  @classmethod
  def eager_query(cls, **kwargs):
    """Eager Query."""
    query = cls.eager_inclusions(super(Snapshot, cls).eager_query(**kwargs),
                                 Snapshot._include_links)
    options = {
        # Revision is loaded here with event's action
        # for performance purpose
        'revision': orm.subqueryload('revision')
                       .joinedload('event')
                       .load_only('action'),
        'revisions': orm.subqueryload('revisions'),
        'audit': orm.joinedload('audit')
                    .load_only("id", "archived"),
    }
    return cls.populate_query(query, options, **kwargs)

  @hybrid_property
  def update_revision(self):
    return self.revision_id

  @update_revision.setter
  def update_revision(self, value):
    self._update_revision = value
    if value == "latest":
      _set_latest_revisions([self])

  @property
  def parent(self):
    return self.audit

  @parent.setter
  def parent(self, value):
    setattr(self, "audit", value)
    self.parent_type = "Audit"

  @staticmethod
  def _extra_table_args(_):
    return (
        db.UniqueConstraint(
            "parent_type", "parent_id",
            "child_type", "child_id"),
        db.Index("ix_snapshots_parent", "parent_type", "parent_id"),
        db.Index("ix_snapshots_child", "child_type", "child_id"),
    )

  def _check_related_objects(self):
    """Checks that Snapshot mapped only to Audits before deletion"""
    for obj in self.related_objects():
      if obj.type not in ("Audit", "Snapshot"):
        db.session.rollback()
        raise exceptions.Conflict(description="Snapshot should be mapped "
                                              "to Audit only before deletion")
      elif obj.type == "Snapshot":
        rel = relationship.Relationship
        related_originals = db.session.query(rel.query.filter(
            or_(and_(rel.source_id == obj.child_id,
                     rel.source_type == obj.child_type,
                     rel.destination_id == self.child_id,
                     rel.destination_type == self.child_type),
                and_(rel.destination_id == obj.child_id,
                     rel.destination_type == obj.child_type,
                     rel.source_id == self.child_id,
                     rel.source_type == self.child_type)
                )).exists()).scalar()
        if related_originals:
          db.session.rollback()
          raise exceptions.Conflict(description="Snapshot should be mapped to "
                                                "Audit only before deletion")

  def handle_delete(self):
    """Handle model_deleted signal for Snapshot"""
    self._check_related_objects()


class Snapshotable(object):
  """Provide `snapshotted_objects` on for parent objects."""

  @declared_attr
  def snapshotted_objects(cls):  # pylint: disable=no-self-argument
    """Return all snapshotted objects"""
    joinstr = "and_(remote(Snapshot.parent_id) == {type}.id, " \
              "remote(Snapshot.parent_type) == '{type}')"
    joinstr = joinstr.format(type=cls.__name__)
    return db.relationship(
        lambda: Snapshot,
        primaryjoin=joinstr,
        foreign_keys='Snapshot.parent_id,Snapshot.parent_type,',
        backref='{0}_parent'.format(cls.__name__),
        cascade='all, delete-orphan')


def handle_before_flush(session, flush_context, instances):
  """Handle snapshot objects on api post requests."""
  # pylint: disable=unused-argument
  # Arguments here are set in the event listener and are mandatory.

  with benchmark("Snapshot pre flush handler"):

    snapshots = [o for o in session if isinstance(o, Snapshot)]
    if not snapshots:
      return

    with benchmark("Snapshot revert attrs"):
      _revert_attrs(snapshots)

    new_snapshots = []
    for o in snapshots:
      if (getattr(o, "_update_revision", "") == "new" and
         not getattr(o, "was_processed", False)):
        new_snapshots.append(o)
        o.was_processed = True
    if new_snapshots:
      with benchmark("Snapshot post api set revisions"):
        _set_latest_revisions(new_snapshots)
      with benchmark("Snapshot post api ensure relationships"):
        _ensure_program_relationships(new_snapshots)


def _revert_attrs(objects):
  """Revert any modified attributes on snapshot.

  All snapshot attributes that are updatable with API calls should only be
  settable and not editable. This function reverts any possible edits to
  existing values.
  """
  attrs = ["parent_id", "parent_type", "child_id", "child_type"]
  for snapshot in objects:
    for attr in attrs:
      deleted = inspect(snapshot).attrs[attr].history.deleted
      if deleted:
        setattr(snapshot, attr, deleted[0])


def _ensure_program_relationships(snapshots):
  """Ensure that snapshotted object is related to audit program.

  This function is made to handle multiple snapshots for a single audit.
  Args:
    snapshots: list of snapshot objects with child_id, child_type and parent.
  """
  # assert that every parent is an Audit as the code relies on program_id field
  assert {s.parent_type for s in snapshots} == {"Audit"}

  rel = relationship.Relationship

  program_children = {}
  for obj in snapshots:
    program_children.setdefault(obj.parent.program, set()).add(
        (obj.child_type, obj.child_id)
    )

  for program, children_set in program_children.items():
    query = db.session.query(
        rel.destination_type, rel.destination_id
    ).filter(
        and_(
            rel.source_type == "Program",
            rel.source_id == program.id,
            tuple_(rel.destination_type, rel.destination_id).in_(children_set)
        )
    ).union_all(
        db.session.query(
            rel.source_type, rel.source_id
        ).filter(
            and_(
                rel.destination_type == "Program",
                rel.destination_id == program.id,
                tuple_(rel.source_type, rel.source_id).in_(children_set)
            )
        )
    )
    children_set.difference_update(query.all())

    child_objects = {}
    type_ids = {}
    for child in children_set:
      type_ids.setdefault(child[0], set()).add(child[1])
    for child_type, ids in type_ids.items():
      child_model = inflector.get_model(child_type)
      query = child_model.query.filter(child_model.id.in_(ids))
      for child in query:
        child_objects[(child.type, child.id)] = child

    for child in children_set:
      if child in child_objects:
        db.session.add(
            relationship.Relationship(
                source=program,
                destination=child_objects[child],
            )
        )


def _set_latest_revisions(objects):
  """Set latest revision_id for given child_type.

  Args:
    objects: list of snapshot objects with child_id and child_type set.
  """
  pairs = [(o.child_type, o.child_id) for o in objects]
  query = db.session.query(
      func.max(revision.Revision.id, name="id", identifier="id"),
      revision.Revision.resource_type,
      revision.Revision.resource_id,
  ).filter(
      tuple_(
          revision.Revision.resource_type,
          revision.Revision.resource_id,
      ).in_(pairs)
  ).group_by(
      revision.Revision.resource_type,
      revision.Revision.resource_id,
  )
  id_map = {(r_type, r_id): id_ for id_, r_type, r_id in query}
  for o in objects:
    o.revision_id = id_map.get((o.child_type, o.child_id))
    if o.revision_id is None:
      raise exceptions.InternalServerError(errors.MISSING_REVISION)


event.listen(Session, 'before_flush', handle_before_flush)
