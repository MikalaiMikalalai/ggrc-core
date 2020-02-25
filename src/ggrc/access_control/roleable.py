# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Roleable model"""

import logging
from collections import defaultdict
from collections import namedtuple

from sqlalchemy import orm
from sqlalchemy import inspect
from sqlalchemy.ext.declarative import declared_attr
from cached_property import cached_property
from werkzeug.exceptions import BadRequest

from ggrc import db
from ggrc.access_control.list import AccessControlList
from ggrc.access_control import role
from ggrc.fulltext.attributes import CustomRoleAttr
from ggrc.models import reflection
from ggrc.utils import errors
from ggrc.utils import referenced_objects


logger = logging.getLogger(__name__)


AclRecord = namedtuple("AclRecord", "person, acl_item")


class Roleable(object):
  """Roleable Mixin

  Mixin that adds access_control_list property to the parent object. Access
  control list includes a list of AccessControlList objects.
  """

  # pylint: disable=not-an-iterable
  # this pylint disable rule is here because of multiple usages of
  # _access_control_list in this file which gives off a false warning.

  _update_raw = ['access_control_list', ]
  _fulltext_attrs = [CustomRoleAttr('access_control_list'), ]
  _api_attrs = reflection.ApiAttributes(
      reflection.Attribute('access_control_list', True, True, True))
  MAX_ASSIGNEE_NUM = 1
  MAX_VERIFIER_NUM = 1

  _custom_publish = {
      'access_control_list': lambda obj: obj.acl_json,
  }

  def __init__(self, *args, **kwargs):
    for ac_role in role.get_ac_roles_for(self.type).values():
      AccessControlList(
          object=self,
          ac_role=ac_role,
      )
    super(Roleable, self).__init__(*args, **kwargs)

  @declared_attr
  def _access_control_list(cls):  # pylint: disable=no-self-argument
    """access_control_list"""
    current_type = cls.__name__

    joinstr = (
        'and_('
        'foreign(remote(AccessControlList.object_id)) == {type}.id,'
        'AccessControlList.object_type == "{type}",'
        'AccessControlList.parent_id_nn == 0'
        ')'
        .format(type=current_type)
    )

    # Since we have some kind of generic relationship here, it is needed
    # to provide custom joinstr for backref. If default, all models having
    # this mixin will be queried, which in turn produce large number of
    # queries returning nothing and one query returning object.
    backref_joinstr = (
        'remote({type}.id) == foreign(AccessControlList.object_id)'
        .format(type=current_type)
    )

    return db.relationship(
        'AccessControlList',
        primaryjoin=joinstr,
        backref=orm.backref(
            '{}_object'.format(current_type),
            primaryjoin=backref_joinstr,
        ),
        cascade='all, delete-orphan'
    )

  @property
  def access_control_list(self):
    return [
        AclRecord(acp.person, acp.ac_list)
        for acl in self._access_control_list
        for acp in acl.access_control_people
    ]

  @cached_property
  def acr_acl_map(self):
    return {acl.ac_role: acl for acl in self._access_control_list}

  @cached_property
  def acr_name_acl_map(self):
    return {acl.ac_role.name: acl for acl in self._access_control_list}

  @cached_property
  def acr_id_acl_map(self):
    return {acl.ac_role.id: acl for acl in self._access_control_list}

  @access_control_list.setter
  def access_control_list(self, values):
    """Setter function for access control list.

    Args:
        values: List of access control roles or dicts containing json
        representation of custom attribute values.
    """
    if values is None:
      return

    from ggrc.models import person

    for value in values:
      referenced_objects.mark_to_cache(person.Person, value["person"]["id"])
    referenced_objects.rewarm_cache(
        rewarm_type=person.Person,
        skip_cad=True,
        undefer=True,
    )

    persons_by_acl = defaultdict(set)
    for value in values:
      if value["ac_role_id"] not in self.acr_id_acl_map:
        raise BadRequest(errors.BAD_PARAMS)
      person = referenced_objects.get("Person", value["person"]["id"])
      acl = self.acr_id_acl_map[value["ac_role_id"]]
      persons_by_acl[acl].add(person)

    for acl in self._access_control_list:
      acl.update_people(persons_by_acl[acl])

  @classmethod
  def eager_query(cls, **kwargs):
    """Eager Query."""
    query = super(Roleable, cls).eager_query(**kwargs)
    options = {
        "access_control_list": (
            orm.subqueryload('_access_control_list')
               .joinedload("ac_role")
               .undefer_group('AccessControlRole_complete'),
            orm.subqueryload('_access_control_list')
               .joinedload("access_control_people")
               .joinedload("person")
               .undefer_group('Person_complete'))
    }
    return cls.populate_query(query, options, **kwargs)

  @classmethod
  def indexed_query(cls):
    """Query used by the indexer"""
    query = super(Roleable, cls).indexed_query()
    return query.options(
        orm.subqueryload(
            '_access_control_list'
        ).joinedload(
            "ac_role"
        ).load_only(
            "id", "name", "object_type", "internal"
        ),
        orm.subqueryload(
            '_access_control_list'
        ).joinedload(
            "access_control_people"
        ).joinedload(
            "person"
        ).load_only(
            "id", "name", "email"
        ),
    )

  @property
  def acl_json(self):
    """Get json representation of access_control_list.

    This function is a hack to preserve backwards compatibility with old
    revision logs.
    """
    acl_json = []
    for acl in self._access_control_list:
      acl_json.extend(acl.people_json)
    return acl_json

  def log_json(self):
    """Log access control lists values."""
    # pylint: disable=not-an-iterable
    res = super(Roleable, self).log_json()
    res["access_control_list"] = self.acl_json
    return res

  def get_persons_for_rolename(self, role_name):
    """Return list of persons that are valid for send role_name."""
    return [
        acp.person
        for acp in self.acr_name_acl_map[role_name].access_control_people
    ]

  def get_person_ids_for_rolename(self, role_name):
    """Return list of persons that are valid for send role_name."""
    if role_name not in self.acr_name_acl_map:
      # This will be removed
      return []
    acps = self.acr_name_acl_map[role_name].access_control_people
    return [acp.person.id for acp in acps]

  def has_acl_changes(self):
    """Check if the object has had any acl changes in the session.

    Since access_control_list is now a normal property it no longer stores any
    history info that is needed for notifications. This helper function is
    meant to replace history check on access_control_list property.

    Returns:
      boolean flag signifying if there are any access control people changes
      in the current session.
    """
    return any(
        inspect(acl).attrs["access_control_people"].history.has_changes()
        for acl in self._access_control_list
    )

  def has_acr_acl_changed(self, acr_name):
    """Check if the object has had any changes in ACL with `acr_name` role.

    Helper function checking access control list with particular access
    control role `acr_name` for changes in current session. If there is no
    such role on object, `False` will be returned.

    Args:
      acr_name: Name of particular access control role to check for changes.

    Returns:
      Boolean indicating if there are any changes in particular access control
      list in the current session. If there is not any ACL with `acr_name`
      ACR, `False` will be returned.
    """
    if acr_name not in self.acr_name_acl_map:
      return False
    acl = self.acr_name_acl_map[acr_name]
    return inspect(acl).attrs["access_control_people"].history.has_changes()

  def validate_acl(self):
    """Check correctness of access_control_list."""
    for _, acl in self.access_control_list:
      if acl.object_type != acl.ac_role.object_type:
        raise ValueError(
            "Access control list has different object_type '{}' with "
            "access control role '{}'".format(
                acl.object_type,
                acl.ac_role.object_type
            )
        )
    self.validate_role_limit()

  def validate_role_limit(self, _import=False):
    """Validate the number of roles assigned to object

    Args:
      _import: if True than function return list of errors for 'add_error'
    """
    # This can now be fully refactored due to ACP, I am leaving this for the
    # end though.
    validation_errors = []
    count_roles = defaultdict(int)
    for _, acl in self.access_control_list:
      count_roles[acl.ac_role.name] += 1

    for _role in count_roles.keys():
      max_attr = "MAX_{}_NUM".format(_role).upper()
      _max = getattr(self, max_attr) if hasattr(self, max_attr) else None
      if _max and count_roles[_role] > _max:
        message = "{} role must have only {} person(s) assigned".format(_role,
                                                                        _max)
        if _import:
          validation_errors.append((_role, message))
        else:
          raise ValueError(message)
    if _import:
      return validation_errors
    return None

  def add_person_with_role(self, person, ac_role):
    """Add a person to ACL object with a given role."""
    acl = self.acr_acl_map.get(ac_role)
    if not acl:
      logger.warning(
          "Trying to add invalid ac_role '%s' with id %s to %s(%s)",
          getattr(ac_role, "name", None),
          getattr(ac_role, "id", None),
          self.type,
          self.id,
      )
      return
    acl.add_person(person)

  def add_person_with_role_id(self, person, ac_role_id):
    """Add a person to ACL object with a given role id."""
    acl = self.acr_id_acl_map.get(ac_role_id)
    if not acl:
      logger.warning(
          "Trying to add invalid role by id %s to %s(%s)",
          ac_role_id,
          self.type,
          self.id,
      )
      return
    acl.add_person(person)

  def add_person_with_role_name(self, person, ac_role_name):
    """Add a person to ACL object with a given role name."""
    acl = self.acr_name_acl_map.get(ac_role_name)
    if not acl:
      logger.warning(
          "Trying to add invalid role by name %s to %s(%s)",
          ac_role_name,
          self.type,
          self.id,
      )
      return
    acl.add_person(person)

  def get_acl_with_role_name(self, ac_role_name):
    """Get ACL with a given role name."""
    acl = self.acr_name_acl_map.get(ac_role_name)
    if not acl:
      logger.warning(
          "Trying to get invalid role by name %s to %s(%s)",
          ac_role_name,
          self.type,
          self.id,
      )
    return acl
