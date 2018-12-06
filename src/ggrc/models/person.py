# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Module with Person model definition."""

import re
from sqlalchemy.orm import validates
from sqlalchemy.orm import relationship

from ggrc import builder
from ggrc import db
from ggrc import settings
from ggrc.fulltext.mixin import Indexed
from ggrc.models.context import HasOwnContext
from ggrc.models.exceptions import ValidationError
from ggrc.models.deferred import deferred
from ggrc.models.mixins import base
from ggrc.models.mixins import Base, CustomAttributable
from ggrc.models.custom_attribute_definition import CustomAttributeMapable
from ggrc.models import reflection
from ggrc.models.relationship import Relatable
from ggrc.models.utils import validate_option
from ggrc.rbac import SystemWideRoles
from ggrc.models.person_profile import PersonProfile


class Person(CustomAttributable, CustomAttributeMapable, HasOwnContext,
             Relatable, base.ContextRBAC, Base, Indexed, db.Model):
  """Person model definition."""

  def __init__(self, *args, **kwargs):
    """Initialize profile relationship while creating Person instance"""
    super(Person, self).__init__(*args, **kwargs)
    self.profile = PersonProfile()

    self.build_object_context(
        context=1,
        name='Personal Context',
        description=''
    )

  __tablename__ = 'people'

  email = deferred(db.Column(db.String, nullable=False), 'Person')
  name = deferred(db.Column(db.String), 'Person')
  language_id = deferred(db.Column(db.Integer), 'Person')
  company = deferred(db.Column(db.String), 'Person')

  object_people = db.relationship(
      'ObjectPerson', backref='person', cascade='all, delete-orphan')
  language = db.relationship(
      'Option',
      primaryjoin='and_(foreign(Person.language_id) == Option.id, '
      'Option.role == "person_language")',
      uselist=False,
  )
  profile = relationship(
      "PersonProfile",
      uselist=False,
      back_populates="person",
  )

  access_control_people = db.relationship(
      'AccessControlPerson',
      foreign_keys='AccessControlPerson.person_id',
      backref="person",
  )

  @staticmethod
  def _extra_table_args(_):
    return (
        db.Index('ix_people_name_email', 'name', 'email'),
        db.Index('uq_people_email', 'email', unique=True),
    )

  _fulltext_attrs = [
      'company',
      'email',
      'name',
  ]
  _api_attrs = reflection.ApiAttributes(
      'company',
      'email',
      'language',
      'name',
      reflection.Attribute('object_people', create=False, update=False),
      reflection.Attribute('system_wide_role', create=False, update=False),
  )
  _include_links = []
  _aliases = {
      "name": "Name",
      "email": {
          "display_name": "Email",
          "unique": True,
      },
      "company": "Company",
      "user_role": {
          "display_name": "Role",
          "type": "user_role",
          "filter_by": "_filter_by_user_role",
      },
  }

  @classmethod
  def _filter_by_user_role(cls, predicate):
    """Custom filter by user roles."""
    from ggrc_basic_permissions.models import Role, UserRole
    return UserRole.query.join(Role).filter(
        (UserRole.person_id == cls.id) &
        (UserRole.context_id.is_(None)) &  # noqa
        predicate(Role.name)
    ).exists()

  # Methods required by Flask-Login
    # pylint: disable=no-self-use
  def is_authenticated(self):
    return self.system_wide_role != 'No Access'

  @property
  def user_name(self):
    return self.email.split("@")[0]

  def is_active(self):
    # pylint: disable=no-self-use
    return True  # self.active

  def is_anonymous(self):
    # pylint: disable=no-self-use
    return False

  def get_id(self):
    return unicode(self.id)  # noqa

  @validates('language')
  def validate_person_options(self, key, option):
    return validate_option(self.__class__.__name__, key, option,
                           'person_language')

  @validates('email')
  def validate_email(self, _, email):
    """Email property validator."""
    if not Person.is_valid_email(email):
      message = "Email address '{}' is invalid. Valid email must be provided"
      raise ValidationError(message.format(email))
    return email

  @staticmethod
  def is_valid_email(val):
    """Check for valid email.

    Borrowed from Django. Literal form, ipv4 address (SMTP 4.1.3).
    """
    email_re = re.compile(
        r'^[-!#$%&\'*+\\.\/0-9=?A-Z^_`{|}~]+@([-0-9A-Z]+\.)+([0-9A-Z]){2,4}$',
        re.IGNORECASE)
    return email_re.match(val) if val else False

  @classmethod
  def eager_query(cls):
    from sqlalchemy import orm

    # query = super(Person, cls).eager_query()
    # Completely overriding eager_query to avoid eager loading of the
    # modified_by relationship
    return super(Person, cls).eager_query().options(
        orm.joinedload('language'),
        orm.subqueryload('object_people'),
    )

  @classmethod
  def indexed_query(cls):
    from sqlalchemy import orm

    return super(Person, cls).indexed_query().options(
        orm.Load(cls).undefer_group(
            "Person_complete",
        ),
    )

  def _display_name(self):
    return self.email

  @builder.simple_property
  def system_wide_role(self):
    """For choosing the role string to show to the user; of all the roles in
    the system-wide context, it shows the highest ranked one (if there are
    multiple) or "No Access" if there are none.
    """

    if self.email in getattr(settings, "BOOTSTRAP_ADMIN_USERS", []):
      return SystemWideRoles.SUPERUSER

    from ggrc.utils.user_generator import is_external_app_user_email
    if is_external_app_user_email(self.email):
      return SystemWideRoles.SUPERUSER

    role_hierarchy = {
        SystemWideRoles.ADMINISTRATOR: 0,
        SystemWideRoles.EDITOR: 1,
        SystemWideRoles.READER: 2,
        SystemWideRoles.CREATOR: 3,
    }
    unique_roles = set([
        user_role.role.name
        for user_role in self.user_roles
        if user_role.role.name in role_hierarchy
    ])
    if not unique_roles:
      return u"No Access"

    # -1 as default to make items not in this list appear on top
    # and thus shown to the user
    sorted_roles = sorted(unique_roles,
                          key=lambda x: role_hierarchy.get(x, -1))
    return sorted_roles[0]
