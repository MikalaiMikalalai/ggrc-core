# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

import unittest

from ggrc import utils


class TestUtilsFunctions(unittest.TestCase):

  @unittest.skip("Audit-scope objects can't be mapped from outside")
  def test_mapping_rules(self):
    """ Test that all mappings go both ways """
    mappings = utils.rules.get_mapping_rules()
    verificationErrors = []

    for object_name, object_mappings in mappings.items():
      for mapping in object_mappings:
        try:
          # If obj A is in obj B mappings, make sure that obj B is also in
          # obj A mappings
          self.assertIn(
              mapping, mappings,
              "- {} is not in the mappings dict".format(mapping)
          )
          self.assertIn(
              object_name, mappings[mapping],
              "{} not found in {} mappings".format(object_name, mapping)
          )
        except AssertionError as e:
          verificationErrors.append(str(e))

    verificationErrors.sort()
    self.assertEqual(verificationErrors, [])

  def test_merge_dict(self):
    """Test merging two dictionaries."""
    dict1 = {
        "a": {
            "b": {
                "c": 1,
                "d": {
                    "e": 2,
                },
            },
        },
    }
    dict2 = {
        "a": {
            "b": {
                "c": 1,
                "f": {
                    "e": 2
                }
            },
            "g": 3
        },
        "h": 4
    }
    expected_result = {
        "a": {
            "b": {
                "c": 1,
                "d": {
                    "e": 2,
                },
                "f": {
                    "e": 2,
                },
            },
            "g": 3,
        },
        "h": 4,
    }

    result = utils.merge_dict(dict1, dict2)

    self.assertEqual(result, expected_result)

  def test_merge_dicts(self):
    """Test merging more than two dictionaries."""
    dict1 = {
        "a": {
            "b": {
                "c": 1,
                "d": {
                    "e": 2
                }
            }
        }
    }
    dict2 = {
        "a": {
            "b": {
                "c": 1,
                "f": {
                    "e": 2
                }
            },
            "g": 3
        },
        "h": 4
    }
    dict3 = {
        "a": {
            "eeb": {
                "c": 1,
                "f": {
                    "e": 2
                }
            },
            "g": 3
        },
        "h": 4
    }

    result = {
        "a": {
            "b": {
                "c": 1,
                "d": {
                    "e": 2,
                },
                "f": {
                    "e": 2,
                },
            },
            "eeb": {
                "c": 1,
                "f": {
                    "e": 2
                }
            },
            "g": 3,
        },
        "h": 4,
    }
    expected_result = utils.merge_dicts(dict1, dict2, dict3)
    self.assertEqual(result, expected_result)

  def test_iso_to_us_date(self):
    """Test ISO to US date format conversion."""
    self.assertEqual(utils.iso_to_us_date("2002-07-11"), "07/11/2002")
    with self.assertRaises(ValueError):
      utils.iso_to_us_date("1002-07-11")
