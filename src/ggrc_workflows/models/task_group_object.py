# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""A module containing the workflow TaskGroupObject model."""


from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext import hybrid
from sqlalchemy import orm

from ggrc import db
from ggrc.models.mixins import Base
from ggrc.models.mixins import base
from ggrc.models.mixins import Timeboxed
from ggrc.models import reflection
from ggrc.models import utils
from ggrc.models import relationship

from ggrc.access_control import roleable


class TaskGroupObject(roleable.Roleable,
                      relationship.Relatable,
                      Timeboxed,
                      base.ContextRBAC,
                      Base,
                      db.Model):
  """Workflow TaskGroupObject model."""

  __tablename__ = 'task_group_objects'

  task_group_id = db.Column(
      db.Integer,
      db.ForeignKey('task_groups.id', ondelete="CASCADE"),
      nullable=False,
  )
  object_id = db.Column(db.Integer, nullable=False)
  object_type = db.Column(db.String, nullable=False)

  object = utils.JsonPolymorphicRelationship("object_id", "object_type",
                                             "{}_object")

  # This parameter is overridden by workflow backref, but is here to ensure
  # pylint does not complain
  _task_group = None

  @hybrid.hybrid_property
  def task_group(self):
    """Getter for task group foreign key."""
    return self._task_group

  @task_group.setter
  def task_group(self, task_group):
    """Setter for task group foreign key."""
    if not self._task_group and task_group:
      relationship.Relationship(source=task_group, destination=self)
    self._task_group = task_group

  @property
  def workflow(self):
    """Property which returns parent workflow object."""
    return self.task_group.workflow

  @staticmethod
  def _extra_table_args(klass):
    # pylint: disable=unused-argument
    return (
        db.UniqueConstraint('task_group_id', 'object_id', 'object_type'),
        db.Index('ix_task_group_id', 'task_group_id'),
    )

  _api_attrs = reflection.ApiAttributes('task_group', 'object')
  _sanitize_html = []

  @classmethod
  def eager_query(cls, **kwargs):
    """Eager Query."""
    query = super(TaskGroupObject, cls).eager_query(**kwargs)
    options = {
        'task_group': orm.subqueryload('task_group'),
    }
    return cls.populate_query(query, options, **kwargs)

  def _display_name(self):
    return self.object.display_name + '<->' + self.task_group.display_name

  def copy(self, _other=None, **kwargs):
    columns = [
        'task_group', 'object_id', 'object_type'
    ]
    target = self.copy_into(_other, columns, **kwargs)
    return target


class TaskGroupable(object):
  @classmethod
  def late_init_task_groupable(cls):
    def make_task_group_objects(cls):
      cls.task_groups = association_proxy(
          'task_group_objects', 'task_group',
          creator=lambda task_group: TaskGroupObject(
              task_group=task_group,
              object_type=cls.__name__,
          )
      )
      joinstr = 'and_(foreign(TaskGroupObject.object_id) == {type}.id, '\
                'foreign(TaskGroupObject.object_type) == "{type}")'
      joinstr = joinstr.format(type=cls.__name__)
      return db.relationship(
          'TaskGroupObject',
          primaryjoin=joinstr,
          backref='{0}_object'.format(cls.__name__),
          cascade='all, delete-orphan',
      )
    cls.task_group_objects = make_task_group_objects(cls)

  _api_attrs = reflection.ApiAttributes(
      reflection.Attribute('task_groups', create=False, update=False),
      reflection.Attribute('task_group_objects', update=False),
  )

  _include_links = []

  @classmethod
  def eager_query(cls, **kwargs):
    query = cls.eager_inclusions(
        super(TaskGroupable, cls).eager_query(**kwargs),
        TaskGroupable._include_links)
    options = {
        'task_group_objects': orm.subqueryload('task_group_objects')
    }
    return cls.populate_query(query, options, kwargs)
