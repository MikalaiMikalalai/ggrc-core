# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Base for category mixing."""

from sqlalchemy.orm import validates

from ggrc import db
from ggrc.models import reflection
from ggrc.models.deferred import deferred
from ggrc.models.mixins import base
from ggrc.models.mixins import Base


class CategorizedPublishable(object):

  def __init__(self, attr_name, type_name):
    self.attr_name = attr_name
    self.type_name = type_name

  @property
  def rel_class(self):
    import ggrc.models
    return getattr(ggrc.models, self.type_name)

  def __call__(self, updater, obj, json_obj):
    return updater.query_for(self.rel_class, json_obj, self.attr_name, True)


class CategoryBase(base.ContextRBAC, Base, db.Model):
  """Base class for Categories"""
  _table_plural = 'category_bases'
  __tablename__ = 'categories'

  type = db.Column(db.String)
  name = deferred(db.Column(db.String), 'CategoryBase')
  lft = deferred(db.Column(db.Integer), 'CategoryBase')
  rgt = deferred(db.Column(db.Integer), 'CategoryBase')
  depth = deferred(db.Column(db.Integer), 'CategoryBase')
  required = deferred(db.Column(db.Boolean), 'CategoryBase')

  __mapper_args__ = {
      'polymorphic_on': type
  }

  categorizations = db.relationship(
      'ggrc.models.categorization.Categorization',
      backref='category',
      cascade='all, delete-orphan',
  )

  def __str__(self):
    return self.name

  # pylint: disable=unused-argument
  @validates('type')
  def validates_type(self, key, value):
    return self.__class__.__name__

  # REST properties
  _api_attrs = reflection.ApiAttributes(
      'name',
      'type',
      'required',
  )

  @classmethod
  def eager_query(cls):
    query = super(CategoryBase, cls).eager_query()
    return query.options()
