# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""  Review helpers """
import collections
from logging import getLogger
from sqlalchemy.orm import joinedload

from ggrc import db
from ggrc.models import all_models
from ggrc.notifications.common import create_notification_history_obj
from ggrc.notifications.data_handlers import get_object_url

# pylint: disable=invalid-name
logger = getLogger(__name__)

REVIEW_REQUEST_CREATED = "review_request_created"

EmailReviewContext = collections.namedtuple(
    "EmailReviewContext", ["reviewable", "object_url", "email_message"]
)


def get_review_notifications():
  """Get review notification"""
  return all_models.Notification.query.filter(
      all_models.Notification.object_type == all_models.Review.__name__,
      all_models.Notification.runner == all_models.Notification.RUNNER_FAST
  ).options(
      joinedload("notification_type")
  )


def build_review_data(review_notifications):
  """Build data for review notification template

  fast_digest.html
  """
  review_requested_data = collections.defaultdict(dict)
  object_state_reverted_data = collections.defaultdict(dict)
  for notification in review_notifications:
    review = notification.object
    reviewable = review.reviewable
    if not reviewable:
      continue
    link = get_object_url(reviewable)
    fill_review_requested_data(link, review, reviewable, review_requested_data)
    fill_object_state_reverted_data(link, notification,
                                    object_state_reverted_data, review,
                                    reviewable)
  return {
      "review_requested_data": review_requested_data,
      "object_state_reverted_data": object_state_reverted_data
  }


def fill_object_state_reverted_data(link, notification, owners_data, review,
                                    reviewable):
  """
  Roles marked with notify_about_review_status and reviewers should get
  notification if Review status changed to "Unreviewed"
  """
  notif_type_name = notification.notification_type.name
  review_notif_types = all_models.Review.NotificationObjectTypes
  if notif_type_name == review_notif_types.STATUS_UNREVIEWED:
    for person, acl in reviewable.access_control_list:
      if acl.ac_role.notify_about_review_status:
        context = EmailReviewContext(reviewable, link, "")
        owners_data[person][review.id] = context
    for person in reviewable.reviewers:
      context = EmailReviewContext(reviewable, link, "")
      owners_data[person][review.id] = context


def fill_review_requested_data(link, review, reviewable, reviewers_data):
  """Reviewers should get notification that object need to be reviewed"""
  for person, _ in review.access_control_list:
    context = EmailReviewContext(reviewable, link, review.email_message)
    reviewers_data[person][review.id] = context


def move_notifications_to_history(notifications):
  """Move sent notifications to history"""
  for notification in notifications:
    notif_history = create_notification_history_obj(notification)
    db.session.add(notif_history)
    db.session.delete(notification)
