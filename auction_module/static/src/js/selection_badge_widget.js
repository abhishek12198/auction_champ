odoo.define('auction_module.SelectionBadgeWidget', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');

    /**
     * SelectionBadgeWidget – renders a Selection field as a row of clickable
     * badge pills instead of radio buttons or a dropdown.
     *
     * Usage in views:  <field name="myField" widget="selection_badge"/>
     */
    var SelectionBadgeWidget = AbstractField.extend({
        className: 'o_field_selection_badge',
        supportedFieldTypes: ['selection'],

        events: {
            'click .o_badge_item': '_onBadgeClick',
        },

        _renderEdit: function () {
            this._renderBadges(true);
        },

        _renderReadonly: function () {
            this._renderBadges(false);
        },

        _disabledTeamIds: function () {
            var fieldName = this.nodeOptions && this.nodeOptions.disabled_teams_field;
            var raw = fieldName && this.recordData ? this.recordData[fieldName] : '';
            var ids = {};
            if (!raw) {
                return ids;
            }
            String(raw).split(',').forEach(function (part) {
                var id = part.trim();
                if (id) {
                    ids[id] = true;
                }
            });
            return ids;
        },

        _renderBadges: function (editable) {
            var self = this;
            var disabled = this._disabledTeamIds();
            this.$el.empty();

            _.each(this.field.selection, function (option) {
                var value = option[0];
                var label = option[1];
                var isDisabled = !!disabled[String(value)];

                var $badge = $('<button type="button">')
                    .addClass('o_badge_item')
                    .text(label)
                    .attr('data-value', value)
                    .attr('aria-pressed', value === self.value ? 'true' : 'false');

                if (value === self.value) {
                    $badge.addClass('o_badge_selected');
                }
                if (isDisabled) {
                    $badge.addClass('o_badge_disabled')
                        .attr('disabled', 'disabled')
                        .attr('aria-disabled', 'true');
                } else if (!editable) {
                    $badge.addClass('o_badge_readonly').attr('disabled', 'disabled');
                }

                self.$el.append($badge);
            });
        },

        _onBadgeClick: function (ev) {
            if (this.mode === 'readonly') { return; }
            if ($(ev.currentTarget).hasClass('o_badge_disabled')) { return; }
            var value = $(ev.currentTarget).data('value');
            this._setValue(value);
        },
    });

    fieldRegistry.add('selection_badge', SelectionBadgeWidget);

    return SelectionBadgeWidget;
});
