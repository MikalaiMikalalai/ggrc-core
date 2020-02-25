# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Mixin for labeled models."""

from sqlalchemy import and_
from sqlalchemy import or_
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.associationproxy import association_proxy

from ggrc import db
from ggrc.models import reflection
from ggrc.models.object_label import ObjectLabel
from ggrc.models.label import Label
from ggrc.fulltext.attributes import MultipleSubpropertyFullTextAttr


class Labeled(object):
  """Mixin to add label in required model."""

  _update_raw = _include_links = ['labels', ]
  _api_attrs = reflection.ApiAttributes(*_include_links)
  _aliases = {
      'labels': 'Labels'
  }

  _fulltext_attrs = [
      MultipleSubpropertyFullTextAttr("label", "labels", ["name"]),
  ]

  @declared_attr
  def _object_labels(cls):  # pylint: disable=no-self-argument
    """Object labels property"""
    # pylint: disable=attribute-defined-outside-init
    cls._labels = association_proxy(
      '_object_labels', 'label',
      creator=lambda label: ObjectLabel(
            label=label,  # noqa
            object_type=cls.__name__
        )
    )
    return db.relationship(
        ObjectLabel,
        primaryjoin=lambda: and_(cls.id == ObjectLabel.object_id,
                                 cls.__name__ == ObjectLabel.object_type),
        foreign_keys=ObjectLabel.object_id,
        backref='{}_labeled'.format(cls.__name__),
        cascade='all, delete-orphan')

  @hybrid_property
  def labels(self):
    return self._labels

  @labels.setter
  def labels(self, values):
    """Setter function for labeled.

    Args:
      values: List of labels in json. Labels mapped on labeled
    and not represented in values will be unmapped from labeled.
    label is represented as a dict {"id": <label id>, "name": <label name>}
    Currently, FE sends the following info:
      for a newly created label: {"id": None, "name": <label name>}
      for old label: {"id": <label_id>, "name": <label name>}
      for being mapped label: {"id": <label id>}
    """
    if values is None:
      return

    for value in values:
      if 'name' in value:
        value['name'] = value['name'].strip()

    if values:
      new_ids = {value['id'] for value in values if value['id']}
      new_names = {value['name'] for value in values if 'name' in value}
      # precache labels
      filter_group = []
      if new_ids:
        filter_group.append(Label.id.in_(new_ids))
      if new_names:
        filter_group.append(Label.name.in_(new_names))
      cached_labels = Label.query.filter(
          and_(or_(*filter_group),
               Label.object_type == self.__class__.__name__)).all()
    else:
      new_ids = set()
      new_names = set()
      cached_labels = []

    old_ids = {label.id for label in self.labels}
    self._unmap_labels(old_ids - new_ids, new_names)
    self._map_labels(new_ids - old_ids, cached_labels)
    # label comparison has to be case insensitive
    if new_names:
      self._add_labels_by_name(new_names, new_ids | old_ids, cached_labels)

  def _map_labels(self, ids, cached_labels):
    """Attach new labels to current object."""
    labels_dict = {label.id: label for label in cached_labels}
    for id_ in ids:
      self._labels.append(labels_dict[id_])

  def _add_labels_by_name(self, names, ids, cached_labels):
    """Creates new labels and map them to current object"""
    labels_dict = {label.name.lower(): label for label in cached_labels}
    for name in names:
      if name.lower() in labels_dict:
        if labels_dict[name.lower()].id in ids:
          continue
        label = labels_dict[name.lower()]
      else:
        label = Label(name=name, object_type=self.__class__.__name__)
      self._labels.append(label)

  def _unmap_labels(self, ids, names):
    """Remove labels from current object."""
    values_map = {
        label.id: label
        for label in self._labels  # noqa pylint: disable=not-an-iterable
    }
    lower_names = [name.lower() for name in names]
    for id_ in ids:
      if values_map[id_].name.lower() not in lower_names:
        self._labels.remove(values_map[id_])

  def log_json(self):
    """Log label values."""
    # pylint: disable=not-an-iterable
    res = super(Labeled, self).log_json()
    res["labels"] = [
        value.log_json() for value in self.labels]
    return res

  @classmethod
  def eager_query(cls, **kwargs):
    """Eager query classmethod."""
    query = super(Labeled, cls).eager_query(**kwargs)
    options = {
        'labels': orm.subqueryload('_object_labels'),
    }
    return cls.populate_query(query, options, **kwargs)

  @classmethod
  def indexed_query(cls):
    return super(Labeled, cls).indexed_query().options(
        orm.subqueryload("_object_labels"))
