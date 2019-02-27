# Copyright (C) 2019 Google Inc.

# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""Unittests for Revision model """

import unittest

import mock
import ddt

from ggrc.models.proposal import FullInstanceContentFased


@ddt.ddt
class TestFullInstanceContentFased(unittest.TestCase):
  """Check FullInstanceContentFased functionality."""

  # pylint: disable=unused-argument
  @ddt.data(({}, {}),
            ({'mapping_list_fields': {}}, {'mapping_list_fields': {}}),
            ({'mapping_list_fields': {'object_people': {}}},
             {'mapping_list_fields': {}}))
  @ddt.unpack
  @mock.patch('flask.g')
  def test_object_people_handling(self, content, res, flask_g):
    """Test non actual for Proposals object_people field."""
    obj = FullInstanceContentFased()
    data = mock.MagicMock()
    with mock.patch("ggrc.utils.revisions_diff.builder.prepare",
                    return_value=content):
      result_content = obj.prepare(data)
      self.assertEqual(result_content, res)
