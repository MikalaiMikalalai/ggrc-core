# Copyright (C) 2020 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
"""Mentioning person smoke tests."""
# pylint: disable=no-self-use
# pylint: disable=too-many-arguments
# pylint: disable=unused-argument
# pylint: disable=invalid-name

import pytest

from lib.constants import element
from lib.rest_facades import person_rest_facade
from lib.service import webui_facade, webui_service
from lib.ui import mentioning_ui_facade
from lib.utils import random_utils, string_utils
from lib.service import rest_facade


class TestMentioningPerson(object):
  """Tests of mentioning person."""

  @pytest.fixture(scope="function")
  def people(self):
    """Creates 10 people."""
    for _ in xrange(10):
      person_rest_facade.create_person()

  @pytest.mark.smoke_tests
  @pytest.mark.parametrize('first_symbol', [string_utils.Symbols.PLUS,
                                            string_utils.Symbols.AT_SIGN])
  def test_mentioning_on_asmt_comments_panel(
      self, people, audit, assessment, selenium, first_symbol, soft_assert
  ):
    """Checks mentioning on assessment comment panel on info panel.

    Preconditions:
        - Program created via REST API.
        - Audit created under Program via REST API.
        - Assessment created under Audit via REST API.
        - 10 People created via REST API.
    """
    mentioning_ui_facade.check_mentioning_on_asmt_comments_panel(
        selenium, soft_assert, audit, assessment, first_symbol)

  @pytest.mark.parametrize('first_symbol', [string_utils.Symbols.PLUS,
                                            string_utils.Symbols.AT_SIGN])
  def test_mention_list_does_not_appear(
      self, audit, assessment, selenium, first_symbol
  ):
    """Checks if the mentioning list does not appear when there is no search
     result on comments panel on assessment info panel.

    Firstly call mention list, then additionally type some trash symbols and
    check that dropdown disappears.
        Preconditions:
        - Program created via REST API.
        - Audit created under Program via REST API.
        - Assessment created under Audit via REST API.
    """
    comment_input = (webui_service.AssessmentsService(selenium).
                     open_info_panel_of_mapped_obj(
                         src_obj=audit, obj=assessment).comments_panel.
                     comment_input)
    comment_input.call_email_dropdown(first_symbol)
    comment_input.fill(text=random_utils.get_string())
    assert comment_input.emails_dropdown.wait_until_disappears()

  @pytest.mark.smoke_tests
  @pytest.mark.parametrize('first_symbol', [string_utils.Symbols.PLUS,
                                            string_utils.Symbols.AT_SIGN])
  @pytest.mark.parametrize('modal', [webui_facade.open_propose_changes_modal,
                                     webui_facade.open_request_review_modal])
  def test_mentioning_on_request_review_and_propose_changes(
      self, people, selenium, first_symbol, soft_assert, modal, program
  ):
    """Checks mentioning on Propose change modal and on Request review modal
    of Program.

    Preconditions:
         - Program created via REST API.
         - 10 People created via REST API.
    """
    mentioning_ui_facade.check_mentioning_on_modals(
        selenium, modal, program, first_symbol, soft_assert)

  @pytest.mark.smoke_tests
  @pytest.mark.parametrize('first_symbol', [string_utils.Symbols.PLUS,
                                            string_utils.Symbols.AT_SIGN])
  def test_mentioning_on_lca_w_required_comment_of_asmt(
      self, people, selenium, soft_assert, first_symbol,
      program, control_mapped_to_program, audit
  ):
    """Checks mentioning on local custom attribute with required comment of
    assessment.

    Objects structure:
      -> Program.
        -> Control mapped to program.
        -> Audit.
          -> Assessment template with dropdown with required comment.
            -> Autogenerated assessment based on template and control.
    """
    assessment_template_w_dropdown = rest_facade.create_asmt_template(
        audit, cad_type=element.AdminWidgetCustomAttributes.DROPDOWN,
        dropdown_types_list=["comment"])
    assessment = rest_facade.create_asmt_from_template(
        audit, assessment_template_w_dropdown, [control_mapped_to_program])
    mentioning_ui_facade.check_mentioning_on_comment_of_lca_dropdown(
        assessment, selenium, first_symbol, soft_assert)
