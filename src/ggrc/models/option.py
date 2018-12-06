# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

from ggrc import db
from ggrc.models.deferred import deferred
from ggrc.models.mixins import base
from ggrc.models.mixins import Base, Described
from ggrc.models import reflection


class Option(Described, base.ContextRBAC, Base, db.Model):
  __tablename__ = 'options'

  role = db.Column(db.String)
  # TODO: inherit from Titled mixin (note: title is nullable here)
  title = db.Column(db.String)
  required = deferred(db.Column(db.Boolean), 'Option')

  def __str__(self):
    return self.title

  @staticmethod
  def _extra_table_args(cls):
    return (
        db.Index('ix_options_role', 'role'),
    )

  _api_attrs = reflection.ApiAttributes('role', 'title', 'required')
