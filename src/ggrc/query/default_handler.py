# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""This module contains special query helper class for query API."""

from ggrc.builder import json
from ggrc.query.builder import QueryHelper
from ggrc.models import inflector
from ggrc.utils import benchmark


# pylint: disable=too-few-public-methods

class DefaultHandler(QueryHelper):
  """Helper class for handling request queries for query API.

  query object = [
    {
      # the same parameters as in QueryHelper
      type: "values", "ids" or "count" - the type of results requested
      fields: [ a list of fields to include in JSON if type is "values" ]
    }
  ]

  After the query is done (by `get_results` method), the results are appended
  to each query object:

  query object with results = [
    {
      # the same fields as in QueryHelper
      values: [ filtered objects in JSON ] (present if type is "values")
      ids: [ ids of filtered objects ] (present if type is "ids")
      count: the number of objects filtered, after "limit" is applied
      total: the number of objects filtered, before "limit" is applied
  """

  def get_results(self):
    """Filter the objects and get their information.

    Updates self.query items with their results. The type of results required
    is read from "type" parameter of every object_query in self.query.

    Returns:
      list of dicts: same query as the input with requested results that match
                     the filter.
    """
    for object_query in self.query:
      query_type = object_query.get("type", "values")
      if query_type not in {"values", "ids", "count"}:
        raise NotImplementedError("Only 'values', 'ids' and 'count' queries "
                                  "are supported now")
      model = inflector.get_model(object_query["object_name"])
      if query_type == "values":
        with benchmark("Get result set: get_results > _get_objects"):
          objects = self._get_objects(object_query)
        object_query["count"] = len(objects)
        with benchmark("get_results > _get_last_modified"):
          object_query["last_modified"] = self._get_last_modified(model,
                                                                  objects)
        with benchmark("serialization: get_results > _transform_to_json"):
          object_query["values"] = self._transform_to_json(
              objects,
              object_query.get("fields"),
          )
      else:
        with benchmark("Get result set: get_results -> _get_ids"):
          ids = self._get_ids(object_query)
        object_query["count"] = len(ids)
        object_query["last_modified"] = None  # synonymous to now()
        if query_type == "ids":
          object_query["ids"] = ids
    return self.query

  @staticmethod
  def _transform_to_json(objects, fields=None):
    """Make a JSON representation of objects from the list."""
    objects_json = [json.publish(obj, attribute_whitelist=fields)
                    for obj in objects]
    objects_json = json.publish_representation(objects_json)
    if fields:
      objects_json = [{f: o.get(f) for f in fields}
                      for o in objects_json]
    return objects_json

  @staticmethod
  def _get_last_modified(model, objects):
    """Get the time of last update of an object in the list."""
    if not objects or not hasattr(model, "updated_at"):
      return None
    return max(obj.updated_at for obj in objects)
