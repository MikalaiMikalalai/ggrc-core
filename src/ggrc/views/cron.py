# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

""" Cron job endpoints initialization and running stuff """

from logging import getLogger
from traceback import format_exc

from ggrc import extensions
from ggrc import login
from ggrc.notifications import common


# pylint: disable=invalid-name
logger = getLogger(__name__)


def send_error_notification(message):
  """Send error notification to APPENGINE_EMAIL user."""
  try:
    user_email = common.get_app_engine_email()
    common.send_email(user_email, "Error in nightly cron job", message)
  except:  # pylint: disable=bare-except
    logger.exception("Failed on sending notification")


def run_job(job):
  """Execute the provided job.

     Failure on job will just logged and don't stop runner.
  """
  try:
    job()
  except:  # pylint: disable=bare-except
    logger.exception("Job '%s' failed", job.__name__)
    send_error_notification(
        "Job '%s' failed with: \n%s" % (job.__name__, format_exc())
    )


def job_runner(name):
  """Run all contributed jobs from all extension modules"""
  cron_jobs = extensions.get_module_contributions(name)
  for job in cron_jobs:
    run_job(job)
  return 'Ok'


def nightly_cron_endpoint():
  """Endpoint running nightly jobs from all modules."""
  return job_runner("NIGHTLY_CRON_JOBS")


def hourly_issue_tracker_sync_endpoint():
  """Endpoint running hourly jobs from all modules."""
  return job_runner("HOURLY_CRON_JOBS")


def half_hour_cron_endpoint():
  """Endpoint running half hourly jobs from all modules"""
  return job_runner("HALF_HOUR_CRON_JOBS")


def import_health_cron_endpoint():
  """Endpoint running ten minute jobs from all modules."""
  return job_runner("IMPORT_EXPORT_JOBS")


def init_cron_views(app):
  """Init all cron jobs' endpoints"""
  app.add_url_rule(
      "/nightly_cron_endpoint", "nightly_cron_endpoint",
      view_func=login.cron_required(nightly_cron_endpoint))

  app.add_url_rule(
      "/hourly_issue_tracker_sync_endpoint",
      "hourly_issue_tracker_sync_endpoint",
      view_func=login.cron_required(hourly_issue_tracker_sync_endpoint)
  )

  app.add_url_rule(
      "/half_hour_cron_endpoint", "half_hour_cron_endpoint",
      view_func=login.cron_required(half_hour_cron_endpoint)
  )

  app.add_url_rule(
      "/import_health_cron_endpoint", "import_health_cron_endpoint",
      view_func=login.cron_required(import_health_cron_endpoint)
  )
