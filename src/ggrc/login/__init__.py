# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""ggrc.login

Provides basic login and session management using Flask-Login with various
backends
"""

import datetime
import json
import logging
import re
from functools import wraps
from werkzeug.exceptions import Forbidden

import flask_login
from flask import g
from flask import request
from flask import redirect
from ggrc.extensions import get_extension_module_for
from ggrc.rbac import SystemWideRoles
from ggrc import settings


logger = logging.getLogger(__name__)


def get_login_module():
  return get_extension_module_for('LOGIN_MANAGER', False)


def user_loader(user_id):
  """Returns the auth user by user_id"""
  from ggrc.utils.user_generator import find_user_by_id
  user = find_user_by_id(user_id)
  if user and settings.DEBUG:
    from google.appengine.api import users
    try:
      ae_user = users.get_current_user()
    except AssertionError:
      ae_user = None
    if ae_user and ae_user.email() != user.email:
      return None
  return user


def init_app(app):
  """Initialize Flask_Login LoginManager with our app"""
  login_module = get_login_module()
  if not login_module:
    return

  login_manager = flask_login.LoginManager()
  login_manager.init_app(app)
  # login_manager.session_protection = 'strong'

  # pylint: disable=unused-variable
  @app.login_manager.unauthorized_handler
  def unauthorized():
    """Redirects to the login page and generates an error.

    Called when the user tries to access an endpoint guarded with
    login_required but they are not authorized.

    Endpoints like /dashboard, /program/1, etc. redirect the user to the
    /login page.

    Endpoints like /api /query, /import, etc. resolve with 401 UNAUTHORIZED
    and a simple json error object.
    """
    if (re.match(r'^(\/api|\/query|\/search)', request.path) or
       request.headers.get('X-Requested-By') == 'GGRC'):
      return json.dumps({'error': 'unauthorized'}), 401
    return redirect(flask_login.login_url('/login', request.url))

  app.route('/login')(login_module.login)
  app.route('/logout')(login_module.logout)

  app.login_manager.user_loader(user_loader)
  if hasattr(login_module, 'before_request'):
    app.before_request(login_module.before_request)
  if hasattr(login_module, 'request_loader'):
    app.login_manager.request_loader(login_module.request_loader)
  # app.context_processor(login_module.session_context)


def get_current_user(use_external_user=True):
  """Gets current user.

  Retrieves the current logged-in user or the external user given
  in the X-external-user header based on the provided flag.

  Args:
    use_external_user: indicates should we use external user or not.

  Returns:
    current user.
  """

  logged_in_user = _get_current_logged_user()
  if use_external_user and is_external_app_user():
    try:
      from ggrc.utils.user_generator import parse_user_email
      external_user_email = parse_user_email(request,
                                             "X-external-user",
                                             mandatory=False)
      if external_user_email:
        from ggrc.utils.user_generator import find_user
        ext_user = find_user(external_user_email, modifier=logged_in_user.id)
        if ext_user:
          return ext_user
    except RuntimeError:
      logger.info("Working outside of request context.")
  return logged_in_user


def _get_current_logged_user():
  """Gets current logged-in user."""
  if hasattr(g, '_current_user'):
    return getattr(g, '_current_user')
  if get_login_module():
    return flask_login.current_user
  return None


def get_current_user_id(use_external_user=True):
  """Gets current user id.

  Retrieves the current logged-in user id or the external user id
  based on the provided flag.

  Args:
    use_external_user: indicates should we use external user or not.

  Returns:
    current user id.
  """
  user = get_current_user(use_external_user)
  if user and not user.is_anonymous():
    return user.id
  return None


def login_required(func):
  """Decorator for functions that require users to be logged in."""
  if get_login_module():
    return flask_login.login_required(func)
  return func


def admin_required(func):
  """Admin rights required decorator.

  Raises:
     Forbidden: if the current user is not an admin.
  """
  @wraps(func)
  def admin_check(*args, **kwargs):
    """Helper function that performs the admin check"""
    user = _get_current_logged_user()
    role = getattr(user, 'system_wide_role', None)
    if role not in SystemWideRoles.admins:
      raise Forbidden()
    return func(*args, **kwargs)
  return admin_check


def cron_required(func):
  """CRON required decorator.
  Securing URLs for CRON documentation:
    https://cloud.google.com/appengine/docs/standard/python/config/cron#securing_urls_for_cron

  Raises:
     Forbidden: if not running by CRON and no secret key in request params.
  """
  @wraps(func)
  def cron_header_check(*args, **kwargs):
    """Helper function that performs CRON header check"""
    if not request.headers.get('X-Appengine-Cron'):
      raise Forbidden()
    return func(*args, **kwargs)
  return cron_header_check


def is_creator():
  """Check if the current user has global role Creator."""
  current_user = _get_current_logged_user()
  return (hasattr(current_user, 'system_wide_role') and
          current_user.system_wide_role == SystemWideRoles.CREATOR)


def is_external_app_user():
  """Checks if the current user is an external application.

  Account for external application is defined in settings. External application
  requests require special processing and validations.
  """
  user = _get_current_logged_user()
  if not user or user.is_anonymous():
    return False

  from ggrc.utils.user_generator import is_app_2_app_user_email
  return is_app_2_app_user_email(user.email)


def get_user_date():
  """
    Get current user timezone from HTTP request
    and prepare users current date

  Returns:
      datetime.date()
  """
  user_tz_offset = int(request.headers.get('x-usertimezoneoffset', 0)) / 60
  user_date = (datetime.datetime.now() + datetime.timedelta(
      hours=user_tz_offset)).date()
  return user_date
