# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Utils for event logging"""

import itertools

from datetime import datetime
from logging import getLogger
from flask import request

from ggrc import db
from ggrc import login
from ggrc.models.cache import Cache
from ggrc.models.event import Event
from ggrc.models.revision import Revision
from ggrc.models.mixins.synchronizable import Synchronizable
from ggrc.utils.revisions_diff import builder as revisions_diff

logger = getLogger(__name__)


def _revision_generator(user_id, action, objects):
  """Generate and return revisions bodies for objects."""
  from ggrc.utils import revisions
  for obj in objects:
    content = obj.log_json()
    _populate_content_acl(content)

    rev = revisions.build_revision_body(
        obj.id,
        obj.__class__.__name__,
        content,
        None,
        action,
        user_id,
    )

    _populate_created_updated_at(obj, rev)
    _populate_relationship_fields(obj, rev)
    _populate_is_empty_field(obj, rev, action)

    yield rev


def _get_log_revisions(current_user_id, obj=None, force_obj=False):
  """Generate and return revisions bodies for all cached objects."""
  revisions = []
  cache = Cache.get_cache()
  if not cache:
    return revisions
  modified_objects = set(cache.dirty)
  new_objects = set(cache.new)
  delete_objects = set(cache.deleted)
  all_edited_objects = itertools.chain(cache.new, cache.dirty, cache.deleted)
  relationships_changes = (o for o in all_edited_objects
                           if o.type == "Relationship")
  for rel in relationships_changes:
    documentable = rel.get_related_for("Document")
    if documentable and \
       documentable.type not in ("Comment", "ExternalComment"):
      document = rel.get_related_for(documentable.type)
      if rel in new_objects and document not in documentable.documents:
        documentable.documents.append(document)
      if rel in delete_objects and document in documentable.documents:
        documentable.documents.remove(document)
      if (documentable not in new_objects and
              documentable not in delete_objects):
        modified_objects.add(documentable)

  revisions.extend(_revision_generator(
      current_user_id, "created", cache.new
  ))
  revisions = _sort_relationship_revisions(revisions)
  revisions.extend(_revision_generator(
      current_user_id, "modified", modified_objects
  ))
  if force_obj and obj is not None and obj not in cache.dirty:
    # If the ``obj`` has been updated, but only its custom attributes have
    # been changed, then this object will not be added into
    # ``cache.dirty set``. So that its revision will not be created.
    # The ``force_obj`` flag solves the issue, but in a bit dirty way.
    rev = _revision_generator(current_user_id, "modified", (obj,))
    revisions.extend(rev)
  revisions.extend(_revision_generator(
      current_user_id, "deleted", cache.deleted
  ))
  return revisions


# pylint: disable-msg=too-many-arguments
def log_event(session, obj=None, current_user_id=None, flush=True,
              force_obj=False, event=None):
  """Logs an event on object `obj`.

  Args:
    session: Current SQLAlchemy session (db.session)
    obj: object on which some operation took place
    current_user_id: ID of the user performing operation
    flush: If set to true, flush the session at the start
    force_obj: Used in case of custom attribute changes to force revision write
    event: event object to log
  Returns:
    Uncommitted models.Event instance
  """
  if flush:
    session.flush()
  if current_user_id is None:
    current_user_id = login.get_current_user_id()
  revisions = _get_log_revisions(current_user_id, obj=obj, force_obj=force_obj)
  if obj is None:
    resource_id = 0
    resource_type = None
    action = "BULK"
  else:
    resource_id = obj.id
    resource_type = str(obj.__class__.__name__)
    try:
      action = request.method
    except RuntimeError as exp:
      # Exception should affect the import request.
      action = "BULK"
      logger.warning("Request retrieval has failed: %s", exp.message)

  if not revisions:
    return event
  if event is None:
    event_id_query = Event.__table__.insert().values(
        modified_by_id=current_user_id,
        action=action,
        resource_id=resource_id,
        resource_type=resource_type,
    )
    event_id = db.session.execute(event_id_query).inserted_primary_key[0]
    event = Event.query.get(event_id)
  for rev in revisions:
    rev["event_id"] = event.id
  db.session.execute(Revision.__table__.insert(), revisions)
  return event


def _sort_relationship_revisions(revisions):
  """Sort revisions of relationships to create automapping relationships
  after original mapping"""
  other = [rev for rev in revisions if rev["resource_type"] != "Relationship"]
  rels = [rev for rev in revisions if rev["resource_type"] == "Relationship"]
  rels.sort(key=lambda obj: obj["content"]["automapping_id"])
  return other + rels


def _populate_content_acl(content):
  """Populate access control list in revision content
  Args:
    content(dict): object content
  """
  if "access_control_list" in content and content["access_control_list"]:
    for acl in content["access_control_list"]:
      acl["person"] = {
          "id": acl["person_id"],
          "type": "Person",
          "href": "/api/people/{}".format(acl["person_id"]),
      }


def _populate_created_updated_at(obj, rev):
  """Populate created_at and updated_at revision fields
  Args:
    obj: object instance
    rev(dict): object revision
  """
  if isinstance(obj, Synchronizable):
    if login.is_external_app_user():
      rev["created_at"] = obj.updated_at
      rev["updated_at"] = obj.updated_at
    else:
      prev_rev = revisions_diff.get_latest_revision_content(obj)
      rev["created_at"] = prev_rev['created_at']
      rev["updated_at"] = prev_rev['updated_at']
  else:
    rev["created_at"] = datetime.utcnow().replace(microsecond=0).isoformat()
    rev["updated_at"] = datetime.utcnow().replace(microsecond=0).isoformat()


def _populate_relationship_fields(obj, rev):
  """Populate relationship related revision fields
  Args:
    obj: object instance
    rev(dict): object revision
  """
  for attr in ["source_type",
               "source_id",
               "destination_type",
               "destination_id"]:
    rev[attr] = getattr(obj, attr, None)


def _populate_is_empty_field(obj, rev, action):
  """Populate is_empty revision field
  Args:
    obj: object instance
    rev(dict): object revision
    action(str): revision action
  """
  if action in ("created", "deleted"):
    rev["is_empty"] = False
  else:
    rev["is_empty"] = bool(
        obj and not revisions_diff.changes_present(obj, rev["content"])
    )
