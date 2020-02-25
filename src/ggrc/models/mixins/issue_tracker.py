# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Mixins for issue tracker integration functionality."""

# pylint: disable=unsubscriptable-object
# pylint: disable=using-constant-test

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declared_attr

from ggrc.models import reflection
from ggrc.models.issuetracker_issue import IssuetrackerIssue

from ggrc.builder import simple_property


class IssueTracked(object):
  """IssueTracked mixin.

  Defines a backref in IssueTrackerIssue model named ModelName_issue_tracked.
  """
  # pylint: disable=too-few-public-methods
  _api_attrs = reflection.ApiAttributes(
      reflection.Attribute("issue_tracker", create=False, update=False),
  )

  def __init__(self, *args, **kwargs):
    super(IssueTracked, self).__init__(*args, **kwargs)
    self.init_on_load()

  @orm.reconstructor
  def init_on_load(self):
    """Init object when it is fetched from DB

    SQLAlchemy doesn't call __init__() for objects from DB
    """

    self._warnings = []
    self.is_import = False
    self.issue_tracker_to_import = dict()

  @declared_attr
  def issuetracker_issue(cls):  # pylint: disable=no-self-argument
    """Relationship with the corresponding issue for cls."""
    current_type = cls.__name__

    joinstr = (
        "and_("
        "foreign(remote(IssuetrackerIssue.object_id)) == {type}.id,"
        "IssuetrackerIssue.object_type == '{type}'"
        ")"
        .format(type=current_type)
    )

    # Since we have some kind of generic relationship here, it is needed
    # to provide custom joinstr for backref. If default, all models having
    # this mixin will be queried, which in turn produce large number of
    # queries returning nothing and one query returning object.
    backref_joinstr = (
        "remote({type}.id) == foreign(IssuetrackerIssue.object_id)"
        .format(type=current_type)
    )

    return sa.orm.relationship(
        IssuetrackerIssue,
        primaryjoin=joinstr,
        backref=sa.orm.backref(
            "{}_issue_tracked".format(current_type),
            primaryjoin=backref_joinstr,
        ),
        cascade="all, delete-orphan",
        uselist=False,
    )

  @classmethod
  def eager_query(cls, **kwargs):
    """Define fields to be loaded eagerly to lower the count of DB queries."""
    query = super(IssueTracked, cls).eager_query(**kwargs)
    options = {
        'issuetracker_issue': orm.joinedload('issuetracker_issue'),
    }
    return cls.populate_query(query, options, **kwargs)

  @simple_property
  def issue_tracker(self):
    """Returns representation of issue tracker related info as a dict."""
    issue_info = self.issuetracker_issue
    if issue_info:
      issue_tracker_attrs = issue_info.to_dict(include_issue=True)
    else:
      issue_tracker_attrs = IssuetrackerIssue.get_issuetracker_issue_stub()

    issue_tracker_attrs["_warnings"] = self._warnings
    return issue_tracker_attrs

  def add_warning(self, message):
    self._warnings.append(message)

  @simple_property
  def warnings(self):
    return self._warnings

  def log_json(self):
    """Serialize IssueTracker to JSON"""
    tmp = super(IssueTracked, self).log_json()
    if self.issue_tracker['enabled']:
      tmp["issue_tracker"] = self.issue_tracker
    else:
      tmp["issue_tracker"] = {"enabled": False}
    return tmp


class IssueTrackedWithUrl(IssueTracked):
  """Class that identifies IssueTracked models that have url."""

  _aliases = {
      "component_id": "Component ID",
      "hotlist_id": "Hotlist ID",
      "issue_priority": "Priority",
      "issue_severity": "Severity",
      "issue_title": "Ticket Title",
      "issue_type": "Issue Type",
      "enabled": {
          "display_name": "Ticket Tracker Integration",
          "description": "Allowed values are:\nOn\nOff",
      },
  }


class IssueTrackedWithConfig(IssueTracked):
  """Class that identifies IssueTracked models that have no url."""
  _aliases = {
      "component_id": "Component ID",
      "hotlist_id": "Hotlist ID",
      "issue_priority": "Priority",
      "issue_severity": "Severity",
      "issue_type": "Issue Type",
      "enabled": {
          "display_name": "Ticket Tracker Integration",
          "description": "Allowed values are:\nOn\nOff",
      },
  }


class IssueTrackedWithPeopleSync(object):
  """Mixin that indentifies IssueTracked models with people sync option."""
  # pylint: disable=too-few-public-methods
  _aliases = {
      "people_sync_enabled": {
          "display_name": "Sync people with Ticket Tracker",
          "description": "Check the box to enable sync between "
                         "Audit roles and Ticket Tracker. "
                         "Uncheck the box to disable the sync.",
      },
  }
