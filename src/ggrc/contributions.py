# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Lists of ggrc contributions."""

import ggrc

from ggrc.integrations import synchronization_jobs  # noqa  # pylint: disable=unused-import
from ggrc.notifications import notification_handlers
from ggrc.notifications import data_handlers


CRON_JOB_GETTERS = [
    ggrc.converters.get_jobs_to_register,
    ggrc.gcalendar.get_jobs_to_register,
    ggrc.integrations.get_jobs_to_register,
    ggrc.notifications.get_jobs_to_register,
]


def _gather_cron_job_handlers(name):
  """Gather cron job handlers from application modules where defined."""
  cron_jobs = []
  for getter in CRON_JOB_GETTERS:
    cron_jobs.extend(getter(name))
  return cron_jobs


def register_night_cron_jobs():
  """Register nightly cron job handlers."""
  return _gather_cron_job_handlers("NIGHTLY_CRON_JOBS")


def register_hour_cron_jobs():
  """Register hourly cron job handlers."""
  return _gather_cron_job_handlers("HOURLY_CRON_JOBS")


def register_half_hour_jobs():
  """Register half-hourly cron job handlers."""
  return _gather_cron_job_handlers("HALF_HOUR_CRON_JOBS")


def register_import_export_jobs():
  """Register import-export cron job handlers."""
  return _gather_cron_job_handlers("IMPORT_EXPORT_JOBS")


NIGHTLY_CRON_JOBS = register_night_cron_jobs()


HOURLY_CRON_JOBS = register_hour_cron_jobs()


HALF_HOUR_CRON_JOBS = register_half_hour_jobs()


IMPORT_EXPORT_JOBS = register_import_export_jobs()


NOTIFICATION_LISTENERS = [
    notification_handlers.register_handlers
]


def contributed_notifications():
  """Get handler functions for ggrc notification file types."""
  return {
      "Assessment": data_handlers.get_assignable_data,
      "Comment": data_handlers.get_comment_data,
      "Review": lambda *x, **_: {}
  }
