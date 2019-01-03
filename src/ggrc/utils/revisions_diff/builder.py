# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Builder the prepare diff in special format between current
instance state and proposed content."""

import collections

from flask import g

from ggrc.utils.revisions_diff import meta_info


def get_latest_revision_content(instance):
  """Returns latest revision for instance."""
  from ggrc.models import all_models
  if not hasattr(g, "latest_revision_content"):
    g.latest_revision_content = {}
  key = (instance.type, instance.id)
  content = g.latest_revision_content.get(key)
  if not content:
    content = all_models.Revision.query.filter(
        all_models.Revision.resource_id == instance.id,
        all_models.Revision.resource_type == instance.type
    ).order_by(
        all_models.Revision.created_at.desc(),
        all_models.Revision.id.desc(),
    ).first().content
    g.latest_revision_content[key] = content
  return content


def mark_for_latest_content(type_, id_):
  """Mark type to get lates contnent when it will be needed."""
  if not hasattr(g, "latest_revision_content_markers"):
    g.latest_revision_content_markers = collections.defaultdict(set)
  g.latest_revision_content_markers[type_].add(id_)


def rewarm_latest_content():
  """Rewarm cache for latest content for marked objects."""
  from ggrc.models import all_models
  if not hasattr(g, "latest_revision_content_markers"):
    return
  if not hasattr(g, "latest_revision_content"):
    g.latest_revision_content = {}
  cache = g.latest_revision_content_markers
  del g.latest_revision_content_markers
  if not cache:
    return
  query = all_models.Revision.query.filter(
      all_models.Revision.resource_type == cache.keys()[0],
      all_models.Revision.resource_id.in_(cache[cache.keys()[0]])
  )
  for type_, ids in cache.items()[1:]:
    query = query.union_all(
        all_models.Revision.query.filter(
            all_models.Revision.resource_type == type_,
            all_models.Revision.resource_id.in_(ids)
        ))
  query = query.order_by(
      all_models.Revision.resource_id,
      all_models.Revision.resource_type,
      all_models.Revision.created_at.desc(),
      all_models.Revision.id.desc(),
  )
  key = None
  for revision in query:
    if key == (revision.resource_type, revision.resource_id):
      continue
    key = (revision.resource_type, revision.resource_id)
    g.latest_revision_content[key] = revision.content


def get_person_email(person_id):
  """Returns person email for sent person id."""
  if not hasattr(g, "person_email_cache"):
    from ggrc.models import all_models
    query = all_models.Person.query.values(all_models.Person.id,
                                           all_models.Person.email)
    g.person_email_cache = dict(query)
  return g.person_email_cache[person_id]


def person_obj_by_id(person_id):
  """Generates person dict for sent person id."""
  return {"id": person_id, "email": get_person_email(person_id)}


def generate_person_list(person_ids):
  """Generates list of person dicts for sent person ids."""
  person_ids = sorted([int(p) for p in person_ids])
  return [person_obj_by_id(i) for i in person_ids]


def generate_acl_diff(acrs, proposed, revisioned):
  """Generates acl diff between peoposed and revised.

  Returns dict of dict.
     {
        ACR_ID: {
            u"added": [{
                "id": person_id,
                "email": person_email,
            },
            ...
            ],
            u"deleted": [{
                "id": person_id,
                "email": person_email,
            },
            ...
            ],
        },
        ...
     }
  """
  if not acrs or proposed is None:
    return {}
  proposed_acl = collections.defaultdict(set)
  revision_acl = collections.defaultdict(set)
  acl_ids = set()
  for acl in proposed:
    role_id = int(acl["ac_role_id"])
    proposed_acl[role_id].add(acl["person"]["id"])
    acl_ids.add(role_id)
  for acl in revisioned:
    role_id = int(acl["ac_role_id"])
    revision_acl[role_id].add(acl["person"]["id"])
    acl_ids.add(role_id)
  acl_dict = {}
  for role_id in acl_ids & {a.id for a in acrs}:
    deleted_person_ids = revision_acl[role_id] - proposed_acl[role_id]
    added_person_ids = proposed_acl[role_id] - revision_acl[role_id]
    if added_person_ids or deleted_person_ids:
      acl_dict[role_id] = {
          u"added": generate_person_list(added_person_ids),
          u"deleted": generate_person_list(deleted_person_ids),
      }
  return acl_dict


def get_validated_value(cad, value, object_id):
  """Get valid value that related to specified cad."""
  if isinstance(value, basestring):
    value = value.strip()
    return value, object_id
  if cad.attribute_type == cad.ValidTypes.CHECKBOX:
    value = int(value)
  if value is not None:
    value = unicode(value)
  return value, object_id


def generate_cav_diff(cads, proposed, revisioned):
  """Build diff for custom attributes."""
  if not cads:
    return {}
  if proposed is None:
    return {}
  diff = {}
  proposed_cavs = {
      int(i["custom_attribute_id"]): (
          i["attribute_value"],
          None if i["attribute_object"] is None
          else i["attribute_object"]["id"]
      )
      for i in proposed
  }
  revisioned_cavs = {
      int(i["custom_attribute_id"]): (
          i["attribute_value"],
          None if i["attribute_object"] is None
          else i["attribute_object"]["id"]
      )
      for i in revisioned
  }
  for cad in cads:
    if cad.id not in proposed_cavs:
      continue
    proposed_val = get_validated_value(cad, *proposed_cavs[cad.id])
    if cad.id not in revisioned_cavs:
      revisioned_value = (cad.default_value, None)
    else:
      revisioned_value = revisioned_cavs[cad.id]
    if proposed_val != revisioned_value:
      value, person_id = proposed_val
      person = person_obj_by_id(person_id) if person_id else None
      diff[cad.id] = {
          "attribute_value": value,
          "attribute_object": person,
      }
  return diff


def __mappting_key_function(object_dict):
  return object_dict["id"]


def generate_list_mappings(fields, diff_data, current_data):
  """Generates list mappings."""
  result = {}
  for field in fields:
    key = field.name
    if key not in diff_data:
      continue
    current = current_data.get(key) or []
    current_key_dict = {int(i["id"]): i for i in current}
    diff = diff_data.pop(key, None) or []
    diff_key_set = {int(i["id"]) for i in diff}
    current_diff_set = set(current_key_dict)
    deleted_ids = current_diff_set - diff_key_set
    added_ids = diff_key_set - current_diff_set
    if deleted_ids or added_ids:
      result[key] = {
          u"added": sorted(
              [i for i in diff if int(i["id"]) in added_ids],
              key=__mappting_key_function
          ),
          u"deleted": sorted(
              [i for i in current if int(i["id"]) in deleted_ids],
              key=__mappting_key_function
          ),
      }
  return result


def generate_single_mappings(fields, diff_data, current_data):
  """Generates single mappings."""
  result = {}
  for field in fields:
    key = field.name
    if key not in diff_data:
      continue
    current = current_data.get(key, None) or {"id": None, "type": None}
    diff = diff_data.pop(key, None) or {"id": None, "type": None}
    if current == diff:
      continue
    if diff["id"] is None:
      result[key] = None
    elif current["id"] is None or diff["id"] != current["id"]:
      result[key] = diff
  return result


def generate_fields(fields, proposed_content, current_data):
  """Returns the diff on fields for sent instance and proposaed data."""
  diff = {}
  for field in fields:
    field_name = field.name
    if field_name not in proposed_content:
      continue
    proposed_val = proposed_content[field_name]
    current_val = current_data.get(field_name)
    if proposed_val != current_val:
      diff[field_name] = proposed_val
  return diff


def prepare(instance, content):
  """Prepare content diff for instance and sent content."""
  instance_meta_info = meta_info.MetaInfo(instance)
  current_data = get_latest_revision_content(instance)
  return {
      "fields": generate_fields(
          instance_meta_info.fields,
          content,
          current_data,
      ),
      "access_control_list": generate_acl_diff(
          instance_meta_info.acrs,
          content.get("access_control_list"),
          current_data.get("access_control_list") or [],
      ),
      "custom_attribute_values": generate_cav_diff(
          instance_meta_info.cads,
          content.get("custom_attribute_values"),
          current_data.get("custom_attribute_values") or [],
      ),
      "mapping_fields": generate_single_mappings(
          instance_meta_info.mapping_fields,
          content,
          current_data,
      ),
      "mapping_list_fields": generate_list_mappings(
          instance_meta_info.mapping_list_fields,
          content,
          current_data
      ),
  }
