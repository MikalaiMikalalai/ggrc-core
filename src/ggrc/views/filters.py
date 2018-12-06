# Copyright (C) 2018 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

from ggrc.app import app
import ggrc.views

"""Filters for GRC specific Jinja processing."""


DISPLAY_CLASS_MAPPINGS = {
    'Program': 'program',

    'Control': 'controls',

    'Objective': 'objectives',

    'Directive': 'governance',
    'Contract': 'governance',
    'Policy': 'governance',
    'Regulation': 'governance',
    'Standard': 'governance',

    'Project': 'business',
    'Facility': 'business',
    'Product': 'business',
    'DataAsset': 'business',
    'Market': 'business',
    'System': 'business',
    'Process': 'business',
    'Metric': 'business',
    'TechnologyEnvironment': 'business',
    'ProductGroup': 'business',

    'OrgGroup': 'entities',
    'Person': 'entities',
    'AccessGroup': 'entities',

    'Risk': 'risk',
    'RiskyAttribute': 'risk',
}


def _get_display_class_filter(obj):
  """Return the display class for an instance, model, or name.
  Returns one of 'business', 'governance', 'risk', 'programs',
  'objective', 'control', 'people'
  """
  from ggrc.models.mixins import Base
  from ggrc.models import get_model
  if isinstance(obj, type):
    obj = obj.__name__
  elif isinstance(obj, Base):
    obj = obj.__class__.__name__

  if isinstance(obj, (str, unicode)):
    model = get_model(obj)
    obj = model._inflector.model_singular

  return DISPLAY_CLASS_MAPPINGS.get(obj, "")


def init_filter_views():
  @app.template_filter("with_static_subdomain")
  def with_static_subdomain_filter(path):
    import urlparse
    from flask import request
    from ggrc import settings
    if not getattr(settings, 'APP_ENGINE', False) \
            or not getattr(settings, 'USE_APP_ENGINE_ASSETS_SUBDOMAIN', True):
      return path
    scheme, netloc, _, _, _ = urlparse.urlsplit(request.url_root)
    if not netloc.startswith('static-dot-'):
      netloc = 'static-dot-' + netloc
    return urlparse.urlunsplit((scheme, netloc, path, '', ''))

  @app.template_filter("viewlink")
  def view_link_filter(obj):
    """Create a view link for an object, that navigates
    to its object-view page in the app
    """
    view = getattr(ggrc.views, obj.__class__.__name__, None)
    return view.url_for(obj) if view else None

  @app.template_filter("display_class")
  def get_display_class_filter(obj):
    """Return the display class for an instance, model, or name.
    Returns one of 'business', 'governance', 'risk', 'programs',
    'objective', 'control', 'people'
    """
    return _get_display_class_filter(obj)

  # Additional generic filters
  #

  @app.template_filter("underscore")
  def underscore_filter(s):
    """Change spaces to underscores and make lowercase
    """
    return "_".join(s.lower().split(' '))

  @app.template_filter("nospace")
  def nospace_filter(s):
    """Remove spaces
    """
    return "".join(s.split(' '))

  # pylint: disable=unused-variable
  @app.template_filter('wrap_in_json_parse')
  def wrap_in_json_parse_filter(json_str):
    """Wrap JSON string in JSON.parse(). Original intention was
    to remove sanitization hooks and allow fields to include
    special symbols like '<', '>', '&', etc.
    Usage: ={ some_obj|tojson|wrap_in_json_parse|safe }

    Args:
      json_str: JSON string escaped with Jinja2 tojson filter
    """
    return 'JSON.parse({})'.format(json_str)
