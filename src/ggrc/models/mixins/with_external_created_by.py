# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

""" Module for WithExternalCreatedBy mixin."""

from sqlalchemy import orm
from sqlalchemy.ext.declarative import declared_attr

from ggrc import db
from ggrc import utils as ggrc_utils
from ggrc.fulltext import attributes
from ggrc.models import reflection
from ggrc.models import utils


class WithExternalCreatedBy(object):
  """Mixin which adds external `created_by_id` attribute."""

  created_by_id = db.Column(db.Integer, nullable=False)

  _api_attrs = reflection.ApiAttributes(
      reflection.ExternalUserAttribute('created_by',
                                       force_create=True),
  )

  _custom_publish = {
      'created_by': ggrc_utils.created_by_stub,
  }

  _aliases = {
      "created_by": {
          "display_name": "Created By",
          "mandatory": False,
      },
  }

  _fulltext_attrs = [
      attributes.FullTextAttr(
          "created_by",
          "created_by",
          ["email", "name"],
      ),
  ]

  @declared_attr
  def created_by(cls):  # pylint: disable=no-self-argument
    """Relationship to user referenced by `created_by_id`."""
    return utils.person_relationship(cls.__name__, "created_by_id")

  def log_json(self):
    """Return JSON representation of the instance."""
    res = super(WithExternalCreatedBy, self).log_json()
    res["created_by"] = ggrc_utils.created_by_stub(self)
    return res

  @classmethod
  def eager_query(cls, **kwargs):
    """Return `sqlalchemy.Query` with eagerly loaded `created_by`."""
    query = cls.eager_inclusions(
        super(WithExternalCreatedBy, cls).eager_query(**kwargs),
        cls._include_links)
    options = {
        'created_by': orm.joinedload("created_by"),
    }
    return cls.populate_query(query, options, **kwargs)

  @classmethod
  def indexed_query(cls):
    """Return `sqlalchemy.Query` with eagerly loaded `created_by`."""
    query = super(WithExternalCreatedBy, cls).indexed_query()
    return query.options(
        orm.Load(cls).joinedload(
            "created_by",
        ).load_only(
            "id",
            "email",
            "name",
        ),
    )
