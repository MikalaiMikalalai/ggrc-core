# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Default query builder for /query API.

This class is used to build SqlAlchemy queries and fetch the result ids.
"""

# flake8: noqa
import collections
import datetime
import itertools

import sqlalchemy as sa

from ggrc import db
from ggrc import models
from ggrc.models import inflector
from ggrc.utils import benchmark
from ggrc.rbac import permissions
from ggrc.query import custom_operators
from ggrc.query import pagination
from ggrc.query.exceptions import BadQueryException


# pylint: disable=too-few-public-methods

class QueryHelper(object):

  """Helper class for handling request queries

  Primary use for this class is to get list of object ids for each object type
  defined in the query. All objects must pass the query filters if they are
  defined.

  query object = [
    {
      object_name: search class name,
      permissions: either read or update, if none are given it defaults to read
      order_by: [
        {
          "name": the name of the field by which to do the sorting
          "desc": optional; if True, invert the sorting order
        }
      ]
      limit: [from, to] - limit the result list to a slice result[from, to]
      filters: {
        relevant_filters:
          these filters will return all ids of the "search class name" object
          that are mapped to objects defined in the dictionary inside the list.
          [ list of filters joined by OR expression
            [ list of filters joined by AND expression
              {
                "object_name": class of relevant object,
                "slugs": list of relevant object slugs,
                        optional and if exists will be converted into ids
                "ids": list of relevant object ids
              }
            ]
          ],
        object_filters: {
          TODO: allow filtering by title, description and other object fields
        }
      }
    }
  ]

  After the query is done (by `get_ids` method), the results are appended to
  each query object:

  query object with results = [
    {
      object_name: search class name,
      (all other object query fields)
      ids: [ list of filtered objects ids ]
    }
  ]

  The result fields may or may not be present in the resulting query depending
  on the attributes of `get` method.

  """

  def __init__(self, query):
    self.query = self._clean_query(query)

  def _get_snapshot_child_type(self, object_query):
    """Return child_type for snapshot from a query"""
    return self._find_child_type(
        object_query.get("filters", {}).get("expression"), ""
    )

  def _find_child_type(self, expr, child_type):
    """Search for child_type recursively down the query expression."""
    if child_type:
      return child_type
    left, oper, right = expr.get("left"), expr.get("op", {}), expr.get("right")
    if oper.get("name") == "=":
      if left == "child_type" and isinstance(right, basestring):
        child_type = right
    else:
      for node in (left, right):
        if isinstance(node, dict):
          child_type = self._find_child_type(node, child_type)
    return child_type

  def _find_verified_field(self, expr):
    """Search for "verified" field recursively down the query expression."""
    left, oper, right = expr.get("left"), expr.get("op", {}), expr.get("right")
    if oper.get("name") == "=":
      if left == "verified" and right == "true":
        expr["right"] = "Yes"
      if left == "verified" and right == "false":
        expr["right"] = "No"
    else:
      for node in (left, right):
        if isinstance(node, dict):
          self._find_verified_field(node)
    return expr

  def _clean_query(self, query):
    """ sanitize the query object """
    for object_query in query:
      if "object_name" not in object_query:
        raise BadQueryException("`object_name` required for each object block")
      filters = object_query.get("filters", {}).get("expression")
      self._clean_filters(filters)
      self._macro_expand_object_query(object_query)
    return query

  def _clean_filters(self, expression):
    """Prepare the filter expression for building the query."""
    if not expression or not isinstance(expression, dict):
      return
    slugs = expression.get("slugs")
    if slugs:
      ids = expression.get("ids", [])
      ids.extend(self._slugs_to_ids(expression["object_name"], slugs))
      expression["ids"] = ids
    try:
      expression["ids"] = [int(id_) for id_ in expression.get("ids", [])]
    except ValueError as error:
      # catch missing relevant filter (undefined id)
      if expression.get("op", {}).get("name", "") == "relevant":
        raise BadQueryException(u"Invalid relevant filter for {}".format(
                                expression.get("object_name", "")))
      raise error
    self._clean_filters(expression.get("left"))
    self._clean_filters(expression.get("right"))

  def _expression_keys(self, exp):
    """Return the list of keys specified in the expression."""
    operator_name = exp.get("op", {}).get("name", None)
    if operator_name in ["AND", "OR"]:
      return self._expression_keys(exp["left"]).union(
          self._expression_keys(exp["right"]))
    left = exp.get("left", None)
    if left is not None and isinstance(left, collections.Hashable):
      return set([left])
    return set()

  def _macro_expand_object_query(self, object_query):
    """Expand object query."""
    def expand_task_dates(exp):
      """Parse task dates from the specified expression."""
      if not isinstance(exp, dict) or "op" not in exp:
        return
      operator_name = exp["op"]["name"]
      if operator_name in ["AND", "OR"]:
        expand_task_dates(exp["left"])
        expand_task_dates(exp["right"])
      elif isinstance(exp["left"], (str, unicode)):
        key = exp["left"]
        if key in ["start", "end"]:
          parts = exp["right"].split("/")
          if len(parts) == 3:
            try:
              month, day, year = [int(part) for part in parts]
            except Exception:
              raise BadQueryException(
                  "Date must consist of numbers")
            exp["left"] = key + "_date"
            exp["right"] = datetime.date(year, month, day)
          elif len(parts) == 2:
            month, day = parts
            exp["op"] = {"name": u"AND"}
            exp["left"] = {
                "op": {"name": operator_name},
                "left": "relative_" + key + "_month",
                "right": month,
            }
            exp["right"] = {
                "op": {"name": operator_name},
                "left": "relative_" + key + "_day",
                "right": day,
            }
          elif len(parts) == 1:
            exp["left"] = "relative_" + key + "_day"
          else:
            raise BadQueryException(u"Field {} should be a date of one of the"
                                    u" following forms: DD, MM/DD, MM/DD/YYYY"
                                    .format(key))

    if object_query["object_name"] == "TaskGroupTask":
      filters = object_query.get("filters")
      if filters is not None:
        exp = filters["expression"]
        keys = self._expression_keys(exp)
        if "start" in keys or "end" in keys:
          expand_task_dates(exp)

  def get_ids(self):
    """Get a list of filtered object IDs.

    self.query should contain a list of queries for different objects which
    will get evaluated and turned into a list of object IDs.

    Returns:
      list of dicts: same query as the input with all ids that match the filter
    """
    for object_query in self.query:
      ids = self._get_ids(object_query)
      object_query["ids"] = ids
    return self.query

  @staticmethod
  def _get_revision_type_query(model, permission_type, filter_ids=None):
    """Filter model based on availability of related objects.

    This method is used only when quering revisions. In such case only
    revisions of objects user has right permission on should be returned. It
    means, user must have either right permission on object revision belongs
    to or in case it is revision of a relationship, user must have right
    permission on at least one part of the relationship.
    """
    allowed_resources = permissions.all_resources(permission_type)
    if not allowed_resources:
      return sa.false()

    if filter_ids:
      allowed_resources = [i for i in allowed_resources if i[1] in filter_ids]

    return sa.or_(
        sa.tuple_(
            model.resource_type,
            model.resource_id,
        ).in_(
            allowed_resources,
        ),
        sa.tuple_(
            model.source_type,
            model.source_id,
        ).in_(
            allowed_resources,
        ),
        sa.tuple_(
            model.destination_type,
            model.destination_id,
        ).in_(
            allowed_resources,
        ),
    )

  @staticmethod
  def _get_comments_type_query(model, permission_type):
    """Filter model based on availability of related objects.

    This method is used to request comments related to objects
    that the user has access to.

    Args:
      model: Model for which will be built sqlalchemy filter.
      permission_type: permission type (e.g. 'update', 'read' and e.t.c.).

    Returns:
      sqlalchemy filter for comments related to objects
        that the user has access to.
    """
    allowed_resources = permissions.all_resources(permission_type)
    if not allowed_resources:
      return sa.false()

    return sa.tuple_(model.__name__, model.id).in_(allowed_resources)


  @staticmethod
  def _get_type_query(model, permission_type, filter_ids=None):
    """Filter by contexts and resources

    Prepare query to filter models based on the available contexts and
    resources for the given type of object.
    """
    if permission_type == "read" and permissions.has_system_wide_read():
      return None

    if permission_type == "update" and permissions.has_system_wide_update():
      return None

    if model.__name__ == "Revision":
      # Since revision contains all object data, query API should query only
      # revisions of objects user has right permission on.
      return QueryHelper._get_revision_type_query(model, permission_type,
                                                  filter_ids)

    if model.__name__ == "Comment":
      return QueryHelper._get_comments_type_query(model, permission_type)

    contexts, resources = permissions.get_context_resource(
        model_name=model.__name__, permission_type=permission_type
    )
    if contexts is None:
      return None

    return model.id.in_(resources) if resources else sa.sql.false()

  def _get_objects(self, object_query):
    """Get a set of objects described in the filters."""

    with benchmark("Get ids: _get_objects -> _get_ids"):
      ids = self._get_ids(object_query)
    if not ids:
      return set()

    object_name = object_query["object_name"]
    object_class = inflector.get_model(object_name)
    query = object_class.eager_query(load_related=False,
                                     fields=object_query.get("fields", []))
    query = query.filter(object_class.id.in_(ids))

    with benchmark("Get objects by ids: _get_objects -> obj in query"):
      id_object_map = {obj.id: obj for obj in query}

    with benchmark("Order objects by ids: _get_objects"):
      objects = [id_object_map[id_] for id_ in ids]

    return objects

  @staticmethod
  def _get_revisions_related_ids(revisions):
    """Get ids of all related objects for revisions"""
    result = [[revision.resource_id,
              revision.source_id,
              revision.destination_id,
              revision.id] for revision in revisions]
    return list(itertools.chain.from_iterable(result))

  def _get_filtered_expression(self, expression, object_class,
                               tgt_class, query):
    """Filter query according to expression."""
    with benchmark("Parse filter query: _get_ids > _build_expression"):
      filter_expression = custom_operators.build_expression(
          expression,
          object_class,
          tgt_class,
          self.query
      )
      if filter_expression is not None:
        query = query.filter(filter_expression)
    return query

  def _get_revision_query(self, object_class, expression, object_query):
    """ Get query object for Revision"""
    query = db.session.query(
      object_class.id,
      object_class.destination_id,
      object_class.source_id,
      object_class.resource_id,
    )
    query = self._get_filtered_expression(expression, object_class,
                                          object_class, query)
    related_objects_ids = self._get_revisions_related_ids(query)
    requested_permissions = object_query.get("permissions", "read")
    with benchmark("Get permissions: _get_ids > _get_type_query"):
      type_query = self._get_type_query(object_class,
                                        requested_permissions,
                                        related_objects_ids)
      if type_query is not None:
        query = query.filter(type_query)
    return query

  def _get_ids(self, object_query):
    """Get a set of ids of objects described in the filters."""

    object_name = object_query["object_name"]
    expression = object_query.get("filters", {}).get("expression")

    if expression is None:
      return set()
    object_class = inflector.get_model(object_name)
    if object_class is None:
      return set()
    tgt_class = object_class

    if object_name == "Assessment":
      self._find_verified_field(expression)

    if object_name == "Revision":
      query = self._get_revision_query(object_class, expression, object_query)
    else:
      query = db.session.query(object_class.id)
      if object_name == "Snapshot":
        child_type = self._get_snapshot_child_type(object_query)
        tgt_class = getattr(models.all_models, child_type, object_class)

      requested_permissions = object_query.get("permissions", "read")
      with benchmark("Get permissions: _get_ids > _get_type_query"):
        type_query = self._get_type_query(object_class, requested_permissions)
        if type_query is not None:
          query = query.filter(type_query)
      query = self._get_filtered_expression(
          expression,
          object_class,
          tgt_class,
          query
      )
    if object_query.get("order_by"):
      with benchmark("Sorting: _get_ids > order_by"):
        query = pagination.apply_order_by(
            object_class,
            query,
            object_query["order_by"],
            tgt_class,
        )

    with benchmark("Apply limit"):
      limit = object_query.get("limit")
      if limit:
        limit_query = pagination.apply_limit(query, limit)
        total = pagination.get_total_count(query)
        ids = [obj.id for obj in limit_query]
      else:
        ids = [obj.id for obj in query]
        total = len(ids)
      object_query["total"] = total

    return ids

  @staticmethod
  def _slugs_to_ids(object_name, slugs):
    """Convert SLUG to proper ids for the given objec."""
    object_class = inflector.get_model(object_name)
    if not object_class:
      return []
    ids = [c.id for c in object_class.query.filter(
        object_class.slug.in_(slugs)).all()]
    return ids
