# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""Module for Mega mixin"""
from collections import defaultdict

import flask
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declared_attr

from ggrc import db
from ggrc.builder import simple_property
from ggrc.models import relationship
from ggrc.models import reflection
from ggrc.models.inflector import get_model


class Mega(object):
  """Mixin adds methods for Mega objects
  Mega objects can have mapped objects of the same type"""

  _api_attrs = reflection.ApiAttributes(
      reflection.Attribute('is_mega', create=False, update=False),
  )

  @simple_property
  def is_mega(self):
    """Returns True if object have children"""
    return bool(self._child_relationships)

  @declared_attr
  def _child_relationships(cls):  # pylint: disable=no-self-argument
    """Return relationships to children
    used to eagerly query is_mega property"""
    joinstr = (
        "and_(foreign(Relationship.source_id) == {cls_name}.id,"
        "foreign(Relationship.source_type) == '{cls_name}',"
        "foreign(Relationship.destination_type) == '{cls_name}')"
    )
    return db.relationship(
        "Relationship",
        primaryjoin=joinstr.format(cls_name=cls.__name__),
    )

  @classmethod
  def eager_query(cls, **kwargs):
    """Define fields to be loaded eagerly to lower the count of DB queries."""
    query = super(Mega, cls).eager_query(**kwargs)
    options = {
        'is_mega': sa.orm.subqueryload('_child_relationships')
                         .load_only("id"),
    }
    return cls.populate_query(query, options, **kwargs)

  @classmethod
  def get_all_relatives_ids(cls, _id, direction):
    """Returns ids of relatives for all generations

    Args:
        _id: ID of Mega object
        direction: could be 'parents' or 'children'
    Returns:
        set of ids
    """
    visited = set()
    not_visited = {_id, }
    while not_visited:
      visited.update(not_visited)
      not_visited = cls._get_relatives_for(direction, not_visited)
      not_visited -= visited
    return visited - {_id}

  @classmethod
  def get_relatives_ids(cls, _id, direction):
    """Returns ids of relatives for one generation

    Args:
        _id: ID of Mega object
        direction: could be 'parents' or 'children'
    Returns:
        set of ids
    """
    return cls._get_relatives_for(direction, {_id}) - {_id}

  @classmethod
  def _get_relatives_for(cls, direction, nodes):
    """Return set of ids of relatives of nodes in selected direction

    Args:
        direction: could be 'parents' or 'children'
        nodes: set of mega objects to find relatives for in selected direction
    Returns:
        set of ids"""
    rel = relationship.Relationship

    if direction == "children":
      direction_filter = rel.source_id.in_
      next_nodes_attr = "destination_id"
    elif direction == "parents":
      direction_filter = rel.destination_id.in_
      next_nodes_attr = "source_id"
    else:
      raise ValueError("Unknown value for direction attr")

    relationships = rel.query.filter(
        direction_filter(nodes),
        rel.source_type == cls.__name__,
        rel.destination_type == cls.__name__,
    )
    return set(getattr(r, next_nodes_attr) for r in relationships)

  @staticmethod
  def _is_parent_for(parent, obj):
    """Check that 'parent' is parent for 'obj'
    Cache parents ids for mega"""
    if hasattr(flask.g, "mega_parents_cache"):
      mega_parents_cache = flask.g.mega_parents_cache
    else:
      mega_parents_cache = flask.g.mega_parents_cache = defaultdict(dict)

    if obj.id in mega_parents_cache[obj.type]:
      parents_ids = mega_parents_cache[obj.type][obj.id]
    else:
      obj_model = get_model(obj.type)
      parents_ids = obj_model.get_all_relatives_ids(obj.id, "parents")
      mega_parents_cache[obj.type][obj.id] = parents_ids
    return parent.id in parents_ids

  @classmethod
  def skip_automapping(cls, src, dst, dst_related_obj):
    """Skip automappings from Mega to child"""
    # In case we mapped an object to Mega we should skip
    # mapping of the object to not parent Mega objects
    # In case of cycle mapping, one Mega object could be parent and child
    to_not_parent = (
        dst_related_obj.type == dst.type and
        not cls._is_parent_for(dst_related_obj, dst)
    )
    # In case we mapped Mega to Mega we should skip mappings of
    # dst related object to src, if src is not parent of dst
    from_not_parent = (
        src.type == dst.type and
        not cls._is_parent_for(src, dst)
    )
    return bool(to_not_parent or from_not_parent)
