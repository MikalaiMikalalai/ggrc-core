/*
 Copyright (C) 2020 Google Inc.
 Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>
 */

import loFind from 'lodash/find';
import canStache from 'can-stache';
import canMap from 'can-map';
import canComponent from 'can-component';
import {NAVIGATE_TO_TAB} from '../../events/event-types';
import './tab-panel';
import './tab-link/tab-link';
import '../questionnaire-link/questionnaire-link';
import template from './tab-container.stache';

export default canComponent.extend({
  tag: 'tab-container',
  view: canStache(template),
  leakScope: true,
  viewModel: canMap.extend({
    lastErrorTab: null,
    define: {
      showTabs: {
        type: 'boolean',
        get: function () {
          return !(this.attr('hideOneTab') &&
            this.attr('panels.length') === 1);
        },
      },
    },
    tabOptions: {},
    hideOneTab: true,
    selectedTabIndex: 0,
    panels: [],
    /**
     * Update Panels List setting all panels except selected to inactive state
     * @param {Number} tabIndex - id of activated panel
     */
    setActivePanel: function (tabIndex) {
      this.attr('selectedTabIndex', tabIndex);
      if (this.instance) {
        this.attr('instance.selectedTabIndex', tabIndex);
      }
      this.attr('panels').forEach(function (panel) {
        let isActive = (panel.attr('tabIndex') === tabIndex);
        panel.attr('active', isActive);
        panel.dispatch('updateActiveTab');
      });
    },
    /**
     * Update selected item and set it to the fist item if no previous selection is available
     */
    setDefaultActivePanel: function () {
      let tabIndex = this.attr('selectedTabIndex');
      let panels = this.attr('panels');
      // Select the first panel if tabIndex is not defined
      if (!tabIndex && panels.length) {
        tabIndex = panels[0].attr('tabIndex');
      }
      this.setActivePanel(tabIndex);
    },
    setLastErrorTab: function (tabIndex) {
      this.attr('lastErrorTab', tabIndex);
    },
    navigate(tabId, tabOptions) {
      const panels = this.attr('panels');
      const panel = loFind(panels, (panel) => panel.tabId === tabId);

      if (panel) {
        this.attr('tabOptions', tabOptions);
        this.setActivePanel(panel.tabIndex);
      }
    },
  }),
  events: {
    /**
     * Update Currently selected Tab on each add of Panels
     */
    '{viewModel.panels} panelAdded': function () {
      this.viewModel.setDefaultActivePanel();
    },
    /**
     * Update Currently selected Tab on each remove of Panels
     */
    '{viewModel.panels} panelRemoved': function () {
      this.viewModel.setDefaultActivePanel();
    },
    /**
     * Activate lastErrorTab.
     */
    '{viewModel.instance} switchToErrorPanel': function () {
      this.viewModel.setActivePanel(this.viewModel.lastErrorTab);
    },
    [`{viewModel.instance} ${NAVIGATE_TO_TAB.type}`](el, ev) {
      this.viewModel.navigate(ev.tabId, ev.options);
    },
  },
});
