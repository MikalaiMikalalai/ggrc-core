/*
 Copyright (C) 2020 Google Inc.
 Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
 */

import canStache from 'can-stache';
import canMap from 'can-map';
import canComponent from 'can-component';
import '../comment/comment-input';
import '../comment/comment-add-button';
import '../object-list-item/editable-document-object-list-item';
import '../assessment/attach-button';
import template from './ca-object-modal-content.stache';
import tracker from '../../tracker';
import {getAssigneeType} from '../../plugins/utils/comments-utils';
import pubSub from '../../pub-sub';

export default canComponent.extend({
  tag: 'ca-object-modal-content',
  view: canStache(template),
  leakScope: true,
  viewModel: canMap.extend({
    define: {
      comment: {
        get() {
          return this.attr('content.fields').indexOf('comment') > -1 &&
            this.attr('state.open');
        },
      },
      evidence: {
        get() {
          return this.attr('content.fields').indexOf('attachment') > -1 &&
            this.attr('state.open');
        },
      },
      url: {
        get() {
          return this.attr('content.fields').indexOf('url') > -1 &&
            this.attr('state.open');
        },
      },
      state: {
        value: {
          open: false,
          save: false,
          controls: false,
        },
      },
    },
    isUpdatingEvidences: false,
    isRemovingEvidences: false,
    content: {
      contextScope: {},
      fields: [],
      title: '',
      type: 'dropdown',
      value: null,
      options: [],
      saveDfd: null,
    },
    afterCreation(comment, success) {
      pubSub.dispatch({
        type: 'relatedItemSaved',
        item: comment,
        itemType: 'comments',
      });
    },
    addComment(comment, data) {
      return comment.attr(data)
        .save()
        .done((comment) => {
          this.afterCreation(comment, true);
        })
        .fail((comment) => {
          this.afterCreation(comment, false);
        });
    },
    onCommentCreated(e) {
      let comment = e.comment;
      let instance = this.attr('instance');
      let context = instance.attr('context');

      tracker.start(instance.type,
        tracker.USER_JOURNEY_KEYS.INFO_PANE,
        tracker.USER_ACTIONS.INFO_PANE.ADD_COMMENT_TO_LCA);

      pubSub.dispatch({
        type: 'relatedItemBeforeSave',
        items: [comment.attr({
          assignee_type: getAssigneeType(instance),
        })],
        itemType: 'comments',
      });
      this.attr('content.contextScope.errorsMap.comment', false);
      this.attr('content.contextScope.validation.valid',
        !this.attr('content.contextScope.errorsMap.attachment'));
      this.attr('state.open', false);
      this.attr('state.save', false);

      this.attr('content.saveDfd')
        .then(() => {
          this.addComment(comment, {
            context: context,
            custom_attribute_revision_upd: {
              custom_attribute_value: {
                id: this.attr('content.contextScope.valueId')(),
              },
              custom_attribute_definition: {
                id: this.attr('content.contextScope.id'),
              },
            },
          });
        });
    },
  }),
});
