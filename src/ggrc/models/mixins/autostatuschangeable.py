# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Mixin for automatic status changes"""

import collections
import datetime
import re

from sqlalchemy import event
from sqlalchemy import inspect
from sqlalchemy.orm import session
from sqlalchemy.orm.attributes import get_history

from ggrc.access_control import roleable
from ggrc.models import evidence
from ggrc.models import mixins
from ggrc.models import relationship
from ggrc.models.mixins import statusable
from ggrc.services import signals
from ggrc.utils import benchmark


Transition = collections.namedtuple('Transition',
                                    ['before', 'condition', 'after'])


class AutoStatusChangeable(object):
  """A mixin for automatic status changes.

  Enables automatic transitioning of objects based on mapping.

  FIRST_CLASS_EDIT_MAPPING for tracking of edits of object attributes listed in
    the TRACKED_ATTRIBUTES
  RELATED_OBJ_STATUS_MAPPING for tracking changes in related objects
    (Document, Snapshot, Comment)
  CUSTOM_ATTRS_STATUS_MAPPING for tracking changes in the custom attributes
    local and global.
  ACL_STATUS_TRANSITIONS for tracking changes in access control lists.
  """

  __lazy_init__ = True

  FIRST_CLASS_EDIT_MAPPING = {
      'MONITOR_STATES': {
          statusable.Statusable.DONE_STATE,
          statusable.Statusable.FINAL_STATE
      },
      'TRACKED_ATTRIBUTES': {
          'title',
          'slug',
          'start_date',
          'end_date',
          'design',
          'operationally',
          'assessment_type'
      },
      'RICH_TEXT_ATTRS': {
          'test_plan',
          'notes',
          'description'
      }
  }

  RELATED_OBJ_STATUS_MAPPING = {
      'Evidence': {
          'key': lambda _: 'ALL',
          'mappings': {
              'ALL': {
                  statusable.Statusable.DONE_STATE,
                  statusable.Statusable.FINAL_STATE,
                  statusable.Statusable.START_STATE
              },
          },
          'ignored_attributes': {
              'notes',
              'description',
          },
          'regular_attributes': {
              'updated_at',
              'modified_by_id'
          }
      },
      'Snapshot': {
          'key': lambda _: 'ALL',
          'mappings': {
              'ALL': {
                  statusable.Statusable.DONE_STATE,
                  statusable.Statusable.FINAL_STATE
              },
          },
      },
      'Comment': {
          'key': lambda _: 'ALL',
          'mappings': {
              'ALL': {
                  statusable.Statusable.START_STATE
              },
          },
      },
  }

  CUSTOM_ATTRS_STATUS_MAPPING = {
      'GCA': {
          statusable.Statusable.DONE_STATE,
          statusable.Statusable.FINAL_STATE
      },
      'LCA': {
          statusable.Statusable.DONE_STATE,
          statusable.Statusable.FINAL_STATE,
          statusable.Statusable.START_STATE
      },
  }

  def acl_changed(acr_name):  # pylint: disable=no-self-argument
    return lambda obj: obj.has_acr_acl_changed(acr_name)

  ACL_STATUS_TRANSITIONS = {
      Transition(
          statusable.Statusable.FINAL_STATE,
          acl_changed('Creators'),
          statusable.Statusable.PROGRESS_STATE,
      ),
      Transition(
          statusable.Statusable.FINAL_STATE,
          acl_changed('Assignees'),
          statusable.Statusable.PROGRESS_STATE,
      ),
      Transition(
          statusable.Statusable.FINAL_STATE,
          acl_changed('Verifiers'),
          statusable.Statusable.PROGRESS_STATE,
      ),
      Transition(
          statusable.Statusable.DONE_STATE,
          acl_changed('Creators'),
          statusable.Statusable.PROGRESS_STATE,
      ),
      Transition(
          statusable.Statusable.DONE_STATE,
          acl_changed('Assignees'),
          statusable.Statusable.PROGRESS_STATE,
      ),
      Transition(
          statusable.Statusable.DONE_STATE,
          acl_changed('Verifiers'),
          statusable.Statusable.PROGRESS_STATE,
      ),
  }

  _need_status_reset = False
  _reset_to_status = None

  def schedule_transition(self, transition):
    """Schedule object transition if possible."""
    success = False
    if self.status == transition.before and transition.condition(self):
      self._need_status_reset = True
      self._reset_to_status = transition.after
      success = True
    return success

  def change_status(self):
    """Change object status to obj._reset_to_status value."""
    # pylint: disable=access-member-before-definition,
    # pylint: disable=attribute-defined-outside-init
    if self.status != self._reset_to_status:
      self.status = self._reset_to_status

  @classmethod
  def _check_need_status_change_for_richtext(cls, obj):
    """
    Compares text w/out tags and \n in rich-text fields.

    For such fields (notes, description and test_plan) method compares
    text without <p>, <br> and \n chars in order to have right line breaks
    and consistent auto-status-changeable behavior.
    """
    # pylint: disable=invalid-name
    # pylint: disable=protected-access

    mapping = obj.FIRST_CLASS_EDIT_MAPPING
    for attr in mapping['RICH_TEXT_ATTRS']:
      val = get_history(obj, attr)
      old_val = val.deleted
      new_val = val.added

      old_val = re.sub('<p>|</p>|<br>|\n', '', old_val[0]) \
          if old_val else old_val
      new_val = re.sub('<p>|</p>|<br>|\n', '', new_val[0]) \
          if new_val else new_val
      obj._need_status_reset = old_val != new_val
      obj._reset_to_status = obj.PROGRESS_STATE
      if obj._need_status_reset:
        return

  @staticmethod
  def _date_has_changes(attr):
    """Detect if date attribute changed.

    Date fields are always interpreted as changed because incoming data is
    of type datetime.datetime, while database field has type datetime.date.

    This function normalizes this and performs the correct check.

    Args:
      attr: (datetime.date|datetime.datetime) Attribute value
    Returns:
      A boolean representing if models date attribute really changed.
    """
    if not attr.history.added or not attr.history.deleted:
      return False
    added, deleted = attr.history.added[0], attr.history.deleted[0]
    if isinstance(added, datetime.datetime):
      added = added.date()
    return added != deleted

  @classmethod
  def _has_changes(cls, obj, attr):
    """Detects if object attribute has changes

    Args:
      obj: (db.Model instance) Object on which to perform attribute inspection.
      attr: (string) Attribute to inspect
    Returns:
      A boolean representing if models attribute changed.
    """
    attr = getattr(inspect(obj).attrs, attr)
    if isinstance(attr.value, (datetime.date, datetime.datetime)):
      return cls._date_has_changes(attr)
    return attr.history.has_changes()

  @classmethod
  def _get_target_related(cls, model, rel):
    """Get target, related instances of an model object.

    Autostatuschangeable is target, other side of relation -> related.

    Args:
      model: (db.Model class) Class whose instance we want to retrieve from
        relationship.
      rel: (Relationship) Instance of relationship object.
    Returns:
      tuple of (source, related)
    """
    if rel.source.type == model.__name__:
      return rel.source, rel.destination
    return rel.destination, rel.source

  @classmethod
  def init(cls, model):
    """Initialization method to run after models have been initialized.

    Args:
      model: (db.Model class) Class on which to run set_handlers method.
    """
    cls.set_handlers(model)

  @classmethod
  def handle_first_class_edit(cls, obj):
    """Handles first class edit.

    Performs check whether object received first class edit (ordinary edit)
    that should transition object to PROGRESS_STATE,
    sets obj._need_status_reset to True if the state transition is needed.

    Args:
      obj: (db.Model instance) Object on which to perform operations.
    """
    # pylint: disable=protected-access

    mapping = obj.FIRST_CLASS_EDIT_MAPPING
    has_attr_changes = any(cls._has_changes(obj, attr)
                           for attr in mapping['TRACKED_ATTRIBUTES'])
    has_rich_attr_changes = any(cls._has_changes(obj, attr)
                                for attr in mapping['RICH_TEXT_ATTRS'])

    if obj.status in mapping['MONITOR_STATES'] and has_attr_changes:
      obj._need_status_reset = True
      obj._reset_to_status = obj.PROGRESS_STATE

    if obj.status in mapping['MONITOR_STATES'] and has_rich_attr_changes:
      cls._check_need_status_change_for_richtext(obj)

  @classmethod
  def handle_custom_attribute_edit(cls, obj):
    """Handle custom attributes.

    Detects changes in Global and Local custom attributes and apply rules
    from the CUSTOM_ATTRS_STATUS_MAPPING

    Args:
      obj (db.Model): Object on which we will perform manipulation.
    """
    # pylint: disable=protected-access
    if not isinstance(obj, mixins.CustomAttributable):
      return
    monitor_states = []
    local_ca = []
    global_ca = []
    for value in obj.custom_attribute_values:
      if value.custom_attribute.definition_id:
        local_ca.append(value)
      else:
        global_ca.append(value)
    status_is_changed = inspect(obj).attrs.status.history.has_changes()
    if obj.has_custom_attr_changes(global_ca) and not status_is_changed:
      monitor_states.extend(obj.CUSTOM_ATTRS_STATUS_MAPPING['GCA'])
    if obj.has_custom_attr_changes(local_ca) and not status_is_changed:
      monitor_states.extend(obj.CUSTOM_ATTRS_STATUS_MAPPING['LCA'])
    if obj.status in monitor_states:
      obj._need_status_reset = True
      obj._reset_to_status = obj.PROGRESS_STATE

  @classmethod
  def handle_acl_edit(cls, obj):
    """Handle edit in object's access control lists.

    Performs check whether object has changes in its access control lists that
    should change object status and sets obj._need_status_reset to True if the
    state transition is needed.

    Args:
      obj: `db.Model` instance on which to perform check.
    """
    if not isinstance(obj, roleable.Roleable):
      return
    for transition in cls.ACL_STATUS_TRANSITIONS:
      if obj.schedule_transition(transition):
        break

  @classmethod
  def track_evidence_attrs_edit(cls, obj, related_settings):
    """Track edit in evidence object.
    Args:
      obj: `evidence.Evidence` instance on which to perform check.
      related_settings: track fields map for `obj`
    Returns:
      bool: True if changed `obj` important attrs and
        related object need status changes else False
    """
    is_acl_changed = obj.has_acr_acl_changed('Admin')
    tracked_attrs = (
        {
            attr.key for attr in inspect(obj).attrs
        }.difference(
            related_settings["ignored_attributes"]
        ).difference(
            related_settings["regular_attributes"]
        )
    )
    tracked_attrs_changed = any(
        cls._has_changes(obj, attr) for attr in tracked_attrs)
    return is_acl_changed or tracked_attrs_changed

  @classmethod
  def adjust_status_before_flush(cls, alchemy_session,
                                 flush_context, instances):
    """Reset status of AutoStatusChangeable objects with _need_status_reset.

    Is registered to listen for 'before_flush' events on a later stage.
    """

    # pylint: disable=unused-argument,protected-access
    with benchmark("adjust status before flush"):
      for obj in alchemy_session.identity_map.values():
        if isinstance(obj, AutoStatusChangeable) and obj._need_status_reset:
          obj.change_status()
          obj._need_status_reset = False
          obj._reset_to_status = None

  @staticmethod
  def has_custom_attr_changes(custom_attributes):
    """Check if custom attribute was changed based on history

    Args:
      custom_attributes : list of custom attributes

    Returns:
      bool:  True if custom any attribute was changed else False
    """
    for value in custom_attributes:
      for attr_name in ('attribute_value', 'attribute_object_id'):
        attr_history = inspect(value).attrs.get(attr_name).history

        # Our frontend generates CAVs with attribute_value='' for each missing
        # CAV object in custom_attribute_values. And transition
        # from CAV is None to CAV.attribute_value == '' shouldn't trigger
        # status change, since both mean that the CAV is not filled in.
        # That why we need additional check: 'any(added) or deleted'

        added, _, deleted = attr_history
        if attr_history.has_changes() and (any(added) or deleted):
          return True
    return False

  @classmethod  # noqa: C901  # ignore flake8 method too complex warning
  def set_handlers(cls, model):
    """Sets up handlers of various events

    Args:
      model: Class on which handlers will be set up.
    """

    # pylint: disable=unused-variable
    @signals.Restful.model_put.connect_via(model)
    def handle_object_put(sender, obj=None, src=None, service=None,
                          initial_state=None):
      """Handles object PUT operation

      Handles edit operation submitted to object.
      See blinker library documentation for other parameters (all necessary).

      Args:
        sender: class that sends event
        obj (db.model): Object on which we will perform manipulation.
        src: The original PUT JSON dictionary.
        service: The instance of Resource handling the PUT request.

      """
      # pylint: disable=unused-variable,unused-argument
      cls.handle_first_class_edit(obj)
      cls.handle_custom_attribute_edit(obj)
      cls.handle_acl_edit(obj)

    @signals.Restful.model_posted.connect_via(relationship.Relationship)
    @signals.Restful.model_deleted.connect_via(relationship.Relationship)
    def handle_relationship(sender, obj=None, src=None, service=None):
      """Handle creation of relationships that can change object status.

      For instance adding or removing Documents, Mapping/Unmapping snapshots,
      adding/removing comments moves object back to PROGRESS_STATE.
      See blinker library documentation for other parameters (all necessary).

      Args:
        sender: class that sends event
        obj (db.model): Object on which we will perform manipulation.
        src: The original PUT JSON dictionary.
        service: The instance of Resource handling the PUT request.
      """
      # pylint: disable=unused-argument,unused-variable,protected-access
      endpoints = [obj.source.type, obj.destination.type]
      if model.__name__ not in endpoints:
        return
      target_object, related_object = cls._get_target_related(model, obj)
      related_mapping = cls.RELATED_OBJ_STATUS_MAPPING.get(related_object.type)
      if not related_mapping:
        return
      target_obj_attrs = inspect(target_object).attrs
      if getattr(target_obj_attrs, "status", None) and \
         target_obj_attrs.status.history.has_changes():
        return
      key = related_mapping['key'](related_object)
      monitor_states = related_mapping['mappings'].get(key, set())
      if target_object.status in monitor_states:
        target_object._need_status_reset = True
        target_object._reset_to_status = target_object.PROGRESS_STATE

    # pylint: disable=unused-variable
    @signals.Restful.model_put.connect_via(evidence.Evidence)
    def handle_evidence_relationship(sender, obj=None, src=None, service=None,
                                     initial_state=None):
      """Handle PUT of Evidence.

        See blinker library documentation for other parameters (all necessary).

      Args:
        sender: class that sends event
        obj (db.model): Object on which we will perform manipulation.
        src: The original PUT JSON dictionary.
        service: The instance of Resource handling the PUT request.
      """
      # pylint: disable=unused-argument,unused-variable
      _handle_evidence_action(obj, "PUT")

    @signals.Restful.model_deleted.connect_via(evidence.Evidence)
    def handle_evidence_delete(sender, obj=None, src=None, service=None):
      """Handle DELETE of Evidence.

        See blinker library documentation for other parameters (all necessary).

      Args:
        sender: class that sends event
        obj (db.model): Object on which we will perform manipulation.
        src: The original PUT JSON dictionary.
        service: The instance of Resource handling the PUT request.
      """
      # pylint: disable=unused-argument,unused-variable
      _handle_evidence_action(obj, "DELETE")

    def _handle_evidence_action(obj=None, action="PUT"):
      """Handle PUT and DELETE of Evidence.


      Args:
        obj (db.model): Object on which we will perform manipulation.
        action: str param which contains name of the request method
      """
      # pylint: disable=protected-access
      auto_changeables = obj.related_objects(_types={model.__name__})
      related_settings = cls.RELATED_OBJ_STATUS_MAPPING.get(obj.type)
      key = related_settings['key'](obj)
      monitor_states = related_settings['mappings'].get(key, set())
      need_status_change = cls.track_evidence_attrs_edit(
          obj, related_settings
      ) if action == "PUT" else True
      for auto_changeable in auto_changeables:
        if auto_changeable.status in monitor_states and need_status_change:
          auto_changeable._reset_to_status = auto_changeable.PROGRESS_STATE
          auto_changeable.change_status()


# pylint: disable=fixme
# TODO: find a way to listen for updates only for classes that use
# AutoStatusChangeable, not for every flush event for every session
event.listen(session.Session, 'before_flush',
             AutoStatusChangeable.adjust_status_before_flush)
