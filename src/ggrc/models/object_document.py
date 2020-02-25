# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

""" Module for docuumentable mixins."""
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declared_attr

from ggrc import db
from ggrc.models import reflection
from ggrc.models.relationship import Relationship
from ggrc.models.document import Document
from ggrc.fulltext.attributes import MultipleSubpropertyFullTextAttr


class Documentable(object):
  """Documentable mixin."""

  _include_links = []

  _fulltext_attrs = [
      MultipleSubpropertyFullTextAttr('documents_file', 'documents_file',
                                      ['title', 'link']),
      MultipleSubpropertyFullTextAttr('documents_reference_url',
                                      'documents_reference_url',
                                      ['link']),
  ]

  @declared_attr
  def documents(cls):  # pylint: disable=no-self-argument
    """Return documents related for that instance."""
    return db.relationship(
        Document,
        primaryjoin=lambda: sa.or_(
            sa.and_(
                cls.id == Relationship.source_id,
                Relationship.source_type == cls.__name__,
                Relationship.destination_type == "Document",
            ),
            sa.and_(
                cls.id == Relationship.destination_id,
                Relationship.destination_type == cls.__name__,
                Relationship.source_type == "Document",
            )
        ),
        secondary=Relationship.__table__,
        secondaryjoin=lambda: sa.or_(
            sa.and_(
                Document.id == Relationship.source_id,
                Relationship.source_type == "Document",
            ),
            sa.and_(
                Document.id == Relationship.destination_id,
                Relationship.destination_type == "Document",
            )
        ),
        viewonly=True,
    )

  def get_documents_by_kind(self, kind):
    return [e for e in self.documents
            if e.kind == kind]

  @property
  def documents_file(self):
    """List of documents FILE type"""
    return self.get_documents_by_kind(Document.FILE)

  @property
  def documents_reference_url(self):
    """List of documents REFERENCE_URL type"""
    return self.get_documents_by_kind(Document.REFERENCE_URL)

  @classmethod
  def eager_query(cls, **kwargs):
    """Eager query classmethod."""
    query = cls.eager_inclusions(
        super(Documentable, cls).eager_query(**kwargs),
        Documentable._include_links)
    options = {
        'documents': sa.orm.subqueryload('documents')
                           .undefer_group('Document_complete'),
    }
    return cls.populate_query(query, options, **kwargs)

  @staticmethod
  def _log_docs(documents):
    """Returns serialization of the given docs"""
    return [d.log_json() for d in documents if d]

  def log_json(self):
    """Serialize to JSON"""
    # This query is required to refresh related documents collection after
    # they were mapped to an object. Otherwise python uses cached value,
    # which might not contain newly created documents.
    out_json = super(Documentable, self).log_json()
    out_json["documents_file"] = self._log_docs(self.documents_file)
    out_json["documents_reference_url"] = self._log_docs(
        self.documents_reference_url)
    return out_json

  @classmethod
  def indexed_query(cls):
    return super(Documentable, cls).indexed_query().options(
        sa.orm.subqueryload("documents").load_only(
            "title",
            "link",
            "kind",
        ),
    )


class PublicDocumentable(Documentable):
  _aliases = {
      "documents_file": {
          "display_name": "Document File",
          "type": reflection.AttributeInfo.Type.SPECIAL_MAPPING,
          "description": (
              "New line separated list of evidence links and "
              "titles.\nExample:\n\nhttp://my.gdrive.link/file "
              "Title of the evidence link"
          ),
      },
      "documents_reference_url": {
          "display_name": "Reference URL",
          "type": reflection.AttributeInfo.Type.SPECIAL_MAPPING,
          "description": "New line separated list of Reference URLs.",
      },
  }
