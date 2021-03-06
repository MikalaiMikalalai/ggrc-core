# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""
  Migrate ExternalCustomAttributes back to CustomAttributes tables

Create Date: 2019-11-29 12:38:49.648670
"""
# disable Invalid constant name pylint warning for mandatory Alembic variables.
# pylint: disable=invalid-name

import logging
import sqlalchemy as sa

from alembic import op

from ggrc.migrations.utils import MIGRATION_FAILED_ERROR
from ggrc.migrations.utils import add_to_objects_without_revisions_bulk


# revision identifiers, used by Alembic.
revision = '794ec2bb70b2'
down_revision = '453a3f86e393'


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _get_cad_ids_for_ggrcq(conn):
  """Get IDs of for newly added ecad

  Args:
    conn: base mysql connection

  Returns:
      id_s : list() of selected ids

  """
  query = sa.text(
      """
          SELECT ecad.id FROM external_custom_attribute_definitions as ecad
          WHERE ecad.id NOT IN (
          SELECT ecad.id FROM external_custom_attribute_definitions as ecad
          JOIN custom_attribute_definitions as cad ON
          (cad.id = ecad.id AND cad.definition_type IN ("control", "risk")));
      """
  )
  id_s = [ecad_id for ecad_id, in conn.execute(query)]
  return id_s


def _get_cad_ids_for_ggrcq_ggrc(conn):
  """Get IDs of for old ecad

  Args:
    conn: base mysql connection

  Returns:
      old_ids : list() of selected ids

  """
  query = sa.text(
      """
          SELECT ecad.id FROM external_custom_attribute_definitions as ecad
          JOIN custom_attribute_definitions as cad ON
          (cad.id = ecad.id AND cad.definition_type IN ("control", "risk"));
      """
  )
  old_ids = [ecad_id for ecad_id, in conn.execute(query)]
  return old_ids


def _get_ext_name_for_ggrcq_ggrc(conn):
  """Get external_name, id pairs of for old ecad

  Args:
    conn: base mysql connection

  Returns:
      ext_name : list() of tuples with selected (names, ids)

  """
  query = sa.text(
      """
          SELECT ecad.external_name, ecad.id FROM
          external_custom_attribute_definitions as ecad
          JOIN custom_attribute_definitions as cad ON
          (cad.id = ecad.id AND cad.definition_type IN ("control", "risk"));
      """
  )
  ext_name = [(ename, ecad_id) for ename, ecad_id in conn.execute(query)]
  return ext_name


def _migrate_ecads_from_ggrcq_to_cads(conn, ids):
  """Migrating ecad_s data to CAD table

  Args:
    conn: base mysql connection
    ids: list() of ids

  """
  query = sa.text(
      """
          INSERT INTO custom_attribute_definitions(
              modified_by_id,
              context_id,
              created_at,
              updated_at,
              title,
              helptext,
              placeholder,
              definition_type,
              attribute_type,
              multi_choice_options,
              mandatory,
              previous_id,
              external_name)
          SELECT
              modified_by_id,
              context_id,
              created_at,
              updated_at,
              title,
              helptext,
              placeholder,
              definition_type,
              attribute_type,
              multi_choice_options,
              mandatory,
              id,
              external_name
          FROM external_custom_attribute_definitions as ecad
          WHERE ecad.id IN :ids
      """
  )
  conn.execute(query, ids=ids)


def _update_cads_with_ids_initial_state(conn, ids):
  """Update old cads with previous id

  Args:
    conn: base mysql connection
    ids: list() of ids

  """
  query = sa.text(
      """
          UPDATE custom_attribute_definitions as cad
          SET cad.previous_id = cad.id
          WHERE cad.id IN :ids
      """
  )

  conn.execute(query, ids=ids)


def _update_ext_names_for_ggrcq_ggrc_cads(conn, names_ids):
  """
    Update external names for ggrcq ggrc CADs
  Args:
    conn: base mysql connection
    names_ids: list() of tuples external_names, ids

  """
  query = sa.text(
      """
          UPDATE custom_attribute_definitions as cad
          SET cad.external_name = :name
          WHERE cad.id = :id_
      """
  )

  for name, id_ in names_ids:
    conn.execute(query, id_=id_, name=name)


# pylint: disable=logging-not-lazy
def upgrade():
  """Upgrade database schema and/or data, creating a new revision."""
  conn = op.get_bind()
  trans = conn.begin()

  cad_ids = _get_cad_ids_for_ggrcq(conn)
  initial_state_ids = _get_cad_ids_for_ggrcq_ggrc(conn)
  ext_names_ids = _get_ext_name_for_ggrcq_ggrc(conn)

  try:
    if cad_ids:  # Migrate eCADs
      _migrate_ecads_from_ggrcq_to_cads(conn, cad_ids)
      add_to_objects_without_revisions_bulk(conn,
                                            cad_ids,
                                            "CustomAttributeDefinition")

    if initial_state_ids:  # Update old CADs
      _update_cads_with_ids_initial_state(conn, initial_state_ids)
      _update_ext_names_for_ggrcq_ggrc_cads(conn, ext_names_ids)
      add_to_objects_without_revisions_bulk(conn, initial_state_ids,
                                            "CustomAttributeDefinition",
                                            action="modified")
  except:
    trans.rollback()
    raise UserWarning(MIGRATION_FAILED_ERROR.format(revision))
  else:
    logger.info("%d newly created ECADs was moved to CAD table" % len(cad_ids))
    logger.info("%d cads where updated" % len(initial_state_ids))
    trans.commit()


def downgrade():
  """Downgrade database schema and/or data back to the previous revision."""
  raise NotImplementedError("Downgrade is not supported")
