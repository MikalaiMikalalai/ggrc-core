# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Helper for getting related objects."""

from sqlalchemy import and_
from sqlalchemy import sql

from ggrc import db
from ggrc.extensions import get_extension_modules
from ggrc import models
from ggrc.models import Snapshot
from ggrc.models.relationship import Relationship
from ggrc.snapshotter.rules import Types


def acl_obj_id(object_type, related_type, related_ids, role=None):
  """Handle person object relationships through ACL."""
  if object_type == "Person":
    return db.session.query(models.AccessControlPerson.person_id).join(
        models.AccessControlList
    ).filter(
        (models.AccessControlList.object_type == related_type) &
        (models.AccessControlList.object_id.in_(related_ids)) &
        (models.AccessControlList.parent_id.is_(None)) &
        (models.AccessControlRole.name == role if role else True)
    )
  elif related_type == "Person":
    return db.session.query(models.AccessControlList.object_id).join(
        models.AccessControlPerson
    ).filter(
        (models.AccessControlList.object_type == object_type) &
        (models.AccessControlPerson.person_id.in_(related_ids)) &
        (models.AccessControlList.parent_id.is_(None)) &
        (models.AccessControlRole.name == role if role else True)
    )
  return None


def custom_attribute_mapping(object_type, related_type, related_ids):
  return db.session.query(models.CustomAttributeValue.attributable_id)\
      .filter(
          (models.CustomAttributeValue.attributable_type == object_type) &
          (models.CustomAttributeValue.attribute_value == related_type) &
          models.CustomAttributeValue.attribute_object_id.in_(related_ids))\
      .union(
      db.session.query(models.CustomAttributeValue.attribute_object_id)
      .filter(
          (models.CustomAttributeValue.attribute_value == object_type) &
          (models.CustomAttributeValue.attributable_type == related_type) &
          models.CustomAttributeValue.attributable_id.in_(related_ids)
      )
  )


def get_special_mappings(object_type, related_type, related_ids):
  return [
      acl_obj_id(object_type, related_type, related_ids),
      custom_attribute_mapping(object_type, related_type, related_ids),
  ]


def get_extension_mappings(object_type, related_type, related_ids):
  """Get mappings handler from etenstion modules."""
  queries = []
  for extension in get_extension_modules():
    get_ids = getattr(extension, "contributed_get_ids_related_to", None)
    if callable(get_ids):
      queries.append(get_ids(object_type, related_type, related_ids))
  return queries


def _array_union(queries):
  """ Union of all valid queries in array """
  clean_queries = [q for q in queries if q]
  if not clean_queries:
    return db.session.query(Relationship.source_id).filter(sql.false())

  query = clean_queries.pop()
  return query.union(*clean_queries)


def _assessment_object_mappings(object_type, related_type, related_ids):
  """Get Object ids for audit scope objects and snapshotted objects."""

  if (object_type in Types.scoped | Types.trans_scope and
          related_type in Types.all):

    source_query = db.session.query(
        Relationship.destination_id.label("result_id"),
    ).join(
        Snapshot,
        and_(
            Relationship.source_id == Snapshot.id,
            Relationship.source_type == Snapshot.__name__,
            Relationship.destination_type == object_type,
            Snapshot.child_type == related_type,
            Snapshot.child_id.in_(related_ids),
        )
    )

    destination_query = db.session.query(
        Relationship.source_id.label("result_id"),
    ).join(
        Snapshot,
        and_(
            Relationship.destination_id == Snapshot.id,
            Relationship.destination_type == Snapshot.__name__,
            Relationship.source_type == object_type,
            Snapshot.child_type == related_type,
            Snapshot.child_id.in_(related_ids),
        )
    )

  elif (object_type in Types.all and
        related_type in Types.scoped | Types.trans_scope):
    source_query = db.session.query(
        Snapshot.child_id.label("result_id"),
    ).join(
        Relationship,
        and_(
            Relationship.source_id == Snapshot.id,
            Relationship.source_type == Snapshot.__name__,
            Relationship.destination_type == related_type,
            Relationship.destination_id.in_(related_ids),
            Snapshot.child_type == object_type,
        )
    )

    destination_query = db.session.query(
        Snapshot.child_id.label("result_id"),
    ).join(
        Relationship,
        and_(
            Relationship.destination_id == Snapshot.id,
            Relationship.destination_type == Snapshot.__name__,
            Relationship.source_type == related_type,
            Relationship.source_id.in_(related_ids),
            Snapshot.child_type == object_type,
        )
    )

  else:
    raise Exception(
        "Snapshot relationship called with invalid types.\n"
        "object types: '{}' - '{}'".format(object_type, related_type)
    )

  return source_query.union_all(destination_query)


def _parent_object_mappings(object_type, related_type, related_ids):
  """Get Object ids for audit and snapshotted object mappings."""

  if object_type in Types.parents and related_type in Types.all:
    query = db.session.query(Snapshot.parent_id).filter(
        Snapshot.parent_type == object_type,
        Snapshot.child_type == related_type,
        Snapshot.child_id.in_(related_ids)
    )
  elif related_type in Types.parents and object_type in Types.all:
    query = db.session.query(Snapshot.child_id).filter(
        Snapshot.parent_type == related_type,
        Snapshot.parent_id.in_(related_ids),
        Snapshot.child_type == object_type,
    )
  else:
    raise Exception(
        "Parent relationship called with invalid types.\n"
        "object types: '{}' - '{}'".format(object_type, related_type)
    )

  return query


def get_ids_related_to(object_type, related_type, related_ids=None):
  """ get ids of objects

  Get a list of all ids for object with object_type, that are related to any
  of the objects with type related_type and id in related_ids
  """

  if isinstance(related_ids, (int, long)):
    related_ids = [related_ids]

  if not related_ids:
    return db.session.query(Relationship.source_id).filter(sql.false())

  if (object_type in Types.scoped and related_type in Types.all or
          related_type in Types.scoped and object_type in Types.all):
    return _assessment_object_mappings(
        object_type, related_type, related_ids)

  if (object_type in Types.parents and related_type in Types.all or
          related_type in Types.parents and object_type in Types.all):
    return _parent_object_mappings(
        object_type, related_type, related_ids)

  destination_ids = db.session.query(Relationship.destination_id).filter(
      and_(
          Relationship.destination_type == object_type,
          Relationship.source_type == related_type,
          Relationship.source_id.in_(related_ids),
      )
  )
  source_ids = db.session.query(Relationship.source_id).filter(
      and_(
          Relationship.source_type == object_type,
          Relationship.destination_type == related_type,
          Relationship.destination_id.in_(related_ids),
      )
  )

  queries = [destination_ids, source_ids]
  queries.extend(get_extension_mappings(
      object_type, related_type, related_ids))
  queries.extend(get_special_mappings(
      object_type, related_type, related_ids))

  if (object_type in Types.trans_scope and related_type in Types.all or
          object_type in Types.all and related_type in Types.trans_scope):
    queries.append(_assessment_object_mappings(
        object_type, related_type, related_ids))

  return _array_union(queries)
