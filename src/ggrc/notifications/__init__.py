# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Main notifications module.

This module is used for coordinating email notifications.
"""
import datetime

from ggrc import extensions, db

# changes of some of the attributes are not considered as a modification of
# the obj itself, e.g. metadata not editable by the end user, or changes
# covered by other event types such as "comment created"
# pylint: disable=invalid-name
from ggrc.login import get_current_user_id

IGNORE_ATTRS = frozenset((
    u"_notifications", u"comments", u"context", u"context_id", u"created_at",
    u"custom_attribute_definitions", u"custom_attribute_values",
    u"_custom_attribute_values", u"finished_date", u"id", u"modified_by",
    u"modified_by_id", u"object_level_definitions", u"review_status",
    u"related_destinations", u"related_sources", u"status",
    u"task_group_objects", u"updated_at", u"verified_date", u"audit_id",
    u"custom_attributes", u"display_name",
))


def register_notification_listeners():
  listeners = extensions.get_module_contributions("NOTIFICATION_LISTENERS")
  for listener in listeners:
    listener()


def _get_value(cav, _type):
  """Get value of custom attribute item"""
  if _type == 'Map:Person':
    return cav["attribute_object"]["id"] if cav["attribute_object"] else None
  if _type == 'Checkbox':
    return cav["attribute_value"] == '1'
  return cav["attribute_value"]


def get_updated_cavs(new_attrs, rev_content):
  """Get dict of updated custom attributes of assessment.

    Args:
      new_attrs: dict which contains cads and cavs of the obj
      rev_content: content of the revision of the obj

    Returns:
      names of cavs that have been updated
    """
  cad_list = rev_content.get("custom_attribute_definitions", []) + \
      new_attrs.get("custom_attribute_definitions", [])
  cad_names = {cad["id"]: cad["display_name"] for cad in cad_list}
  cad_types = {cad["id"]: cad["attribute_type"] for cad in cad_list}

  old_cavs = rev_content.get("custom_attribute_values", [])
  new_cavs = new_attrs.get("custom_attribute_values", [])

  old_cavs_dict = {}

  for cav in old_cavs:
    cav_id = cav["custom_attribute_id"]
    if cav_id in cad_names and cav_id in cad_types:
      old_cavs_dict[cad_names[cav_id]] = _get_value(cav, cad_types[cav_id])

  new_cavs = {cad_names[cav["custom_attribute_id"]]:
              _get_value(cav, cad_types[cav["custom_attribute_id"]])
              for cav in new_cavs}

  for attr_name, new_val in new_cavs.iteritems():
    old_val = old_cavs_dict.get(attr_name, None)
    if old_val != new_val:
      if not old_val and not new_val:
        continue
      yield attr_name


def add_notification(obj, notif_type_name):
  """Add notification for object uses notif_type_cache as cache"""
  from ggrc.models import all_models
  notif_type_id = all_models.NotificationType.query.filter_by(
      name=notif_type_name).one().id

  # I don't like to have flush here, but we need a ID for newly created objects
  if not obj.id:
    db.session.flush()

  db.session.add(all_models.Notification(
      object=obj,
      send_on=datetime.datetime.utcnow(),
      notification_type_id=notif_type_id,
      runner=all_models.Notification.RUNNER_FAST,
      modified_by_id=get_current_user_id()
  ))
