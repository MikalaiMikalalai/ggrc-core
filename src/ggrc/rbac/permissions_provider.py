# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

from collections import namedtuple

from flask import g
from flask.ext.login import current_user

from ggrc.app import db
from ggrc.rbac.permissions import permissions_for as find_permissions
from ggrc.rbac.permissions import is_allowed_create
from ggrc.models import get_model, all_models
from ggrc.models import Person

Permission = namedtuple(
    'Permission',
    'action resource_type resource_id context_id'
)

_CONTRIBUTING_RESOURCE_TYPES = {}


def get_contributing_resource_types(resource_type):
  """Return a list of resource types using the same context space.
     This is needed because permissions may be given for, e.g., "Contract", but
     the restriction on join is done knowing only "Directive".
  """
  resource_types = _CONTRIBUTING_RESOURCE_TYPES.get(resource_type, None)
  if resource_types is None:
    resource_types = [resource_type]
    resource_model = get_model(resource_type)
    if resource_model:
      resource_manager = resource_model._sa_class_manager
      resource_types.extend(
          manager.class_.__name__
          for manager in resource_manager.subclass_managers(True)
      )
    _CONTRIBUTING_RESOURCE_TYPES[resource_type] = resource_types
  return resource_types


class DefaultUserPermissionsProvider(object):
  def __init__(self, settings):
    pass

  def permissions_for(self, _):
    return DefaultUserPermissions()


def resolve_permission_variable(value):
  if isinstance(value, str) or isinstance(value, unicode):
    if value.startswith('$'):
      if value == '$current_user':
        return current_user
      if value == '$current_user.id':
        return current_user.id
      raise Exception(
          'The permission condition variable {0} is not defined!'
          .format(value)
      )
    else:
      return value
  else:
    return value


def get_deep_attr(instance, names):
  value = instance
  for name in names.split("."):
    value = getattr(value, name)
  return value


def contains_condition(instance, value, list_property, **_):
  """Check if instance contains a value in a list.
     Example:
        "terms": {
            "list_property": "owners",
            "value": "$current_user"
        },
        "condition": "contains"
  """
  value = resolve_permission_variable(value)
  list_value = get_deep_attr(instance, list_property)
  return value in list_value


def is_condition(instance, value, property_name, **_):
  """Check if instance attribute is of a given value
     Example:
      "terms": {
         "property_name": "person",
         "value": "$current_user"
       },
       "condition": "is"

  """
  value = resolve_permission_variable(value)
  property_value = get_deep_attr(instance, property_name)
  return value == property_value


def relationship_condition(instance, action, property_name, **_):
  if getattr(instance, 'context') is not None:
    context_id = getattr(instance.context, 'id')
  else:
    context_id = None
  for prop in property_name.split(','):
    obj = getattr(instance, prop)
    if context_id is not None and \
       getattr(obj, 'context') is not None and \
       getattr(obj.context, 'id') == context_id and \
       is_allowed_create('Relationship', None, context_id):
      return True
    # Mapping a person does not require a permission check on the Person object
    if isinstance(obj, Person):
      continue
    if not find_permissions()._is_allowed_for(obj, action):
      return False
  return True


def forbid_condition(instance, blacklist, _current_action, **_):
  return instance.type not in blacklist.get(_current_action, ())


def has_not_changed_condition(instance, property_name, prevent_if=None, **_):
  """Check if instance attribute has not changed
     Example:
      "terms": {
         "property_name": "archived",
         "prevent_if": True
       },
       "condition": "has_not_changed"

  """
  if prevent_if and getattr(instance, property_name, False) == prevent_if:
    return False
  return not db.inspect(instance).get_history(
      property_name, False).has_changes()


def has_changed_condition(instance, property_name, prevent_if=None, **_):
  """Check if instance attribute has changed
     Example:
      "terms": {
         "property_name": "archived"
       },
       "condition": "has_changed"

  """
  if getattr(instance, property_name, False) == prevent_if:
    return True
  return db.inspect(instance).get_history(
      property_name, False).has_changes()


def is_auditor(instance, **_):
  """Check if user has auditor role on the audit field of the instance"""
  # pylint: disable=protected-access
  if not hasattr(instance, "audit"):
    return False
  if find_permissions()._is_allowed_for(instance.audit, "update"):
    return True
  exists_query = db.session.query(
      all_models.AccessControlList
  ).join(
      all_models.AccessControlPerson
  ).join(
      all_models.AccessControlRole
  ).filter(
      all_models.AccessControlPerson.person_id == current_user.id,
      all_models.AccessControlList.object_type == instance.audit.type,
      all_models.AccessControlList.object_id == instance.audit.id,
      all_models.AccessControlRole.name == "Auditors",
  ).exists()
  return db.session.query(exists_query).scalar()


def is_workflow_admin(instance, **_):
  """Check if current user has Admin role in scope of parent Workflow object"""
  return any(acl for person, acl in instance.workflow.access_control_list
             if acl.ac_role.name == "Admin" and person == current_user)


def is_allowed_based_on(instance, property_name, action, **_):
  """Check permissions based on permission seted up as attribute instance."""
  related_object = getattr(instance, property_name, None)
  if related_object is None:
    return False
  # pylint: disable=protected-access
  # This is the proper way of getting permissions, but the function is private
  # due to code debt
  return find_permissions()._is_allowed_for(related_object, action)


"""
All functions with a signature

..

  func(instance, **kwargs)
"""
_CONDITIONS_MAP = {
    'contains': contains_condition,
    'is': is_condition,
    'relationship': relationship_condition,
    'forbid': forbid_condition,
    'has_not_changed': has_not_changed_condition,
    'has_changed': has_changed_condition,
    'is_auditor': is_auditor,
    'is_workflow_admin': is_workflow_admin,
    'is_allowed_based_on': is_allowed_based_on,
}


class DefaultUserPermissions(object):
  """Common logic for user permissions."""
  # super user, context_id 0 indicates all contexts
  ADMIN_PERMISSION = Permission(
      '__GGRC_ADMIN__',
      '__GGRC_ALL__',
      None,
      0,
  )

  def _admin_permission_for_context(self, context_id):
    """Create an admin permission object for the given context"""
    return Permission(
        self.ADMIN_PERMISSION.action,
        self.ADMIN_PERMISSION.resource_type,
        None,
        context_id)

  def _permission_match(self, permission, permissions):
    """Check if the user has the given permission"""

    if None in \
        permissions\
            .get(permission.action, {})\
            .get(permission.resource_type, {})\
            .get('contexts', []):
      return True
    return \
        permission.resource_id in permissions\
        .get(permission.action, {})\
        .get(permission.resource_type, {})\
        .get('resources', [])\
        or permission.context_id in \
        permissions\
        .get(permission.action, {})\
        .get(permission.resource_type, {})\
        .get('contexts', [])\
        or permission.context_id in \
        permissions\
        .get(permission.action, {})\
        .get(self.ADMIN_PERMISSION.resource_type, {})\
        .get('contexts', [])

  @staticmethod
  def _permissions():
    """Returns request permission from the global scope"""
    return getattr(g, '_request_permissions', {})

  def _is_allowed(self, permission):
    permissions = self._permissions()
    if permission.context_id \
       and self._is_allowed(permission._replace(context_id=None)):
      return True
    if self._permission_match(permission, permissions):
      return True
    if self._permission_match(self.ADMIN_PERMISSION, permissions):
      return True
    return self._permission_match(
        self._admin_permission_for_context(permission.context_id),
        permissions)

  @staticmethod
  def _check_conditions(instance, action, conditions):
    """Check if any condition is valid for the instance."""
    for condition in conditions:
      func = _CONDITIONS_MAP[str(condition['condition'])]
      terms = condition.setdefault('terms', {})
      if func(instance, _current_action=action, **terms):
        return True
    return False

  def _is_allowed_for(self, instance, action):
    permissions = self._permissions()
    # Check for admin permission
    if self._permission_match(self.ADMIN_PERMISSION, permissions):
      no_context_conditions = permissions[self.ADMIN_PERMISSION.action]\
          .get(self.ADMIN_PERMISSION.resource_type)\
          .get("conditions", {})\
          .get(None, [])
      context_conditions = permissions[self.ADMIN_PERMISSION.action]\
          .get(self.ADMIN_PERMISSION.resource_type)\
          .get("conditions", {})\
          .get(0, [])
      conditions = no_context_conditions + context_conditions
      if not conditions:
        return True
      return self._check_conditions(instance, action, conditions)
    if (not permissions.get(action) or
       not permissions[action].get(instance._inflector.model_singular)):
      return False
    resources = self._permissions()\
        .setdefault(action, {})\
        .setdefault(instance._inflector.model_singular, {})\
        .setdefault('resources', [])
    contexts = self._permissions()\
        .setdefault(action, {})\
        .setdefault(instance._inflector.model_singular, {})\
        .setdefault('contexts', [])
    # We can't use instance.context_id, because it requires the
    # object <-> context mapping to be created,
    # which isn't the case when creating objects
    context_id = None
    if hasattr(instance, 'context') and hasattr(instance.context, 'id'):
      context_id = instance.context.id
    if instance.id in resources:
      return True
    no_context_conditions = self._permissions()\
        .setdefault(action, {})\
        .setdefault(instance._inflector.model_singular, {})\
        .setdefault('conditions', {})\
        .setdefault(None, [])

    context_conditions = self._permissions()\
        .setdefault(action, {})\
        .setdefault(instance._inflector.model_singular, {})\
        .setdefault('conditions', {})\
        .setdefault(context_id, [])
    conditions = no_context_conditions + context_conditions
    # Check any conditions applied per resource
    if (None in contexts or context_id in contexts) and not conditions:
      return True
    return self._check_conditions(instance, action, conditions)

  def is_allowed_create(self, resource_type, resource_id, context_id):
    """Whether or not the user is allowed to create a resource of the specified
    type in the context."""
    return self._is_allowed(
        Permission('create', resource_type, resource_id, context_id))

  def is_allowed_create_for(self, instance):
    """Whether or not the user is allowed to create the given instance"""
    return self._is_allowed_for(instance, 'create')

  def is_allowed_read(self, resource_type, resource_id, context_id):
    """Whether or not the user is allowed to read a resource of the specified
    type in the context."""
    return self._is_allowed(
        Permission('read', resource_type, resource_id, context_id))

  def is_allowed_read_for(self, instance):
    """Whether or not the user is allowed to read the given instance"""
    return self._is_allowed_for(instance, 'read')

  def is_allowed_update(self, resource_type, resource_id, context_id):
    """Whether or not the user is allowed to update a resource of the specified
    type in the context."""
    return self._is_allowed(
        Permission('update', resource_type, resource_id, context_id))

  def is_allowed_update_for(self, instance):
    """Whether or not the user is allowed to update the given instance"""
    return self._is_allowed_for(instance, 'update')

  def is_allowed_delete(self, resource_type, resource_id, context_id):
    """Whether or not the user is allowed to delete a resource of the
    specified type in the context."""
    return self._is_allowed(
        Permission('delete', resource_type, resource_id, context_id))

  def is_allowed_delete_for(self, instance):
    """Whether or not the user is allowed to delete the given instance"""
    return self._is_allowed_for(instance, 'delete')

  def _get_resources_for(self, action, resource_type):
    """Get resources resources (object ids) for a given action and
    resource_type"""
    permissions = self._permissions()

    if self._permission_match(self.ADMIN_PERMISSION, permissions):
      return None

    # Get the list of resources for a given resource type and any
    #   superclasses
    resource_types = get_contributing_resource_types(resource_type)

    ret = []
    for resource_type in resource_types:
      ret.extend(
          permissions
          .get(action, {})
          .get(resource_type, {})
          .get('resources', set()))
    return ret

  def _get_contexts_for(self, action, resource_type):
    # FIXME: (Security) When applicable, we should explicitly assert that no
    #   permissions are expected (e.g. that every user has ADMIN_PERMISSION).
    permissions = self._permissions()

    if self._permission_match(self.ADMIN_PERMISSION, permissions):
      return None

    # Get the list of contexts for a given resource type and any
    #   superclasses
    resource_types = get_contributing_resource_types(resource_type)

    ret = []
    for resource_type in resource_types:
      ret.extend(permissions.get(action, {})
                            .get(resource_type, {})
                            .get('contexts', []))

    # Extend with the list of all contexts for which the user is an ADMIN
    admin_list = list(
        permissions.get(self.ADMIN_PERMISSION.action, {})
        .get(self.ADMIN_PERMISSION.resource_type, {})
        .get('contexts', ()))
    ret.extend(admin_list)
    if None in ret:
      return None
    return ret

  def create_contexts_for(self, resource_type):
    """All contexts in which the user has create permission."""
    return self._get_contexts_for('create', resource_type)

  def read_contexts_for(self, resource_type):
    """All contexts in which the user has read permission."""
    return self._get_contexts_for('read', resource_type)

  def update_contexts_for(self, resource_type):
    """All contexts in which the user has update permission."""
    return self._get_contexts_for('update', resource_type)

  def delete_contexts_for(self, resource_type):
    """All contexts in which the user has delete permission."""
    return self._get_contexts_for('delete', resource_type)

  def create_resources_for(self, resource_type):
    """All resources in which the user has create permission."""
    return self._get_resources_for('create', resource_type)

  def read_resources_for(self, resource_type):
    """All resources in which the user has read permission."""
    return self._get_resources_for('read', resource_type)

  def update_resources_for(self, resource_type):
    """All resources in which the user has update permission."""
    return self._get_resources_for('update', resource_type)

  def delete_resources_for(self, resource_type):
    """All resources in which the user has delete permission."""
    return self._get_resources_for('delete', resource_type)

  def is_admin(self):
    """Whether the user has ADMIN permissions."""
    return self._is_allowed(self.ADMIN_PERMISSION)

  def all_resources(self, action):
    """All resources in which the user has `action` permission."""
    permissions = self._permissions()
    return [
        (res_type, res_id)
        for res_type, permission in permissions.get(action, {}).iteritems()
        for res_id in permission.get("resources", set())
    ]
