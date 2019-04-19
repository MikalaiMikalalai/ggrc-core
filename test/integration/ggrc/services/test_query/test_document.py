# coding: utf-8

# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Tests for /query api endpoint."""

import ddt

from ggrc.models import all_models

from integration.ggrc import TestCase
from integration.ggrc.api_helper import Api
from integration.ggrc.models import factories


@ddt.ddt
class TestDocumentQueries(TestCase):
  """Tests for /query api for Document instance filtering."""

  def setUp(self):
    super(TestDocumentQueries, self).setUp()
    self.api = Api()

  @ddt.data(all_models.Document.FILE,
            all_models.Document.REFERENCE_URL,
            all_models.Document.URL_FOR_ARIANE,
            all_models.Document.URL_FOR_SPUR)
  def test_filter_document_by_type(self, kind):
    """Test filter documents by document type."""
    data = {
        all_models.Document.FILE: factories.DocumentFileFactory().id,
        all_models.Document.REFERENCE_URL:
            factories.DocumentReferenceUrlFactory().id,
        all_models.Document.URL_FOR_ARIANE:
            factories.DocumentURLForArianeFactory().id,
        all_models.Document.URL_FOR_SPUR:
            factories.DocumentURLForSPURFactory().id,
    }
    query_request_data = [{
        u'fields': [],
        u'filters': {
            u'expression': {
                u'left': u'kind',
                u'op': {u'name': u'='},
                u'right': kind,
            }
        },
        u'limit': [0, 5],
        u'object_name': u'Document',
        u'permissions': u'read',
        u'type': u'values',
    }]
    resp = self.api.send_request(self.api.client.post,
                                 data=query_request_data,
                                 api_link="/query")
    self.assertEqual(1, resp.json[0]["Document"]["count"])
    self.assertEqual(data[kind],
                     resp.json[0]["Document"]["values"][0]["id"])
