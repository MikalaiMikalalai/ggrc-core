# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""Module contains Facility model."""

from ggrc import db
from ggrc.access_control.roleable import Roleable
from ggrc.fulltext.mixin import Indexed
from ggrc.models.comment import ScopedCommentable
from ggrc.models import mixins
from ggrc.models.object_document import PublicDocumentable
from ggrc.models.object_person import Personable
from ggrc.models.relationship import Relatable


class Facility(Roleable,
               PublicDocumentable,
               mixins.CustomAttributable,
               Personable,
               Relatable,
               ScopedCommentable,
               mixins.TestPlanned,
               mixins.LastDeprecatedTimeboxed,
               mixins.base.ContextRBAC,
               mixins.ScopeObject,
               mixins.Folderable,
               Indexed,
               db.Model):
  """Facility model"""
  __tablename__ = 'facilities'
  _aliases = {
      "documents_file": None,
      "urls_for_ariane": None,
      "urls_for_spur": None,
  }
