odoo.define('auction_module.SelectionCardWidget', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');

    var MODE_ICONS = {
        linear: 'fa-list-ol',
        random: 'fa-random',
    };

    var THEME_ICON = 'fa-id-card-o';

    /**
     * SelectionCardWidget – renders a Selection field as a responsive grid of
     * selectable cards (Card Theme + Player Call-Up Mode).
     *
     * Options:
     *   allowed_field — Char field with comma-separated allow-list.
     *                   Empty / missing → every option is selectable.
     *                   Values outside the list are shown greyed / locked.
     *   card_style    — 'theme' (default) or 'mode' (icon-led, not colour themes).
     */
    var SelectionCardWidget = AbstractField.extend({
        className: 'o_field_selection_card',
        supportedFieldTypes: ['selection'],

        events: {
            'click .o_sel_card': '_onCardClick',
            'keydown .o_sel_card': '_onCardKeydown',
        },

        /**
         * @override
         */
        reset: function (record, event) {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                var allowedField = self.nodeOptions && self.nodeOptions.allowed_field;
                if (allowedField && event && event.data && event.data.changes
                        && Object.prototype.hasOwnProperty.call(event.data.changes, allowedField)) {
                    self._render();
                }
            });
        },

        _renderEdit: function () {
            this._renderCards(true);
        },

        _renderReadonly: function () {
            this._renderCards(false);
        },

        _getAllowedValues: function () {
            var fieldName = this.nodeOptions && this.nodeOptions.allowed_field;
            if (!fieldName) {
                return null;
            }
            var raw = '';
            if (this.recordData && this.recordData[fieldName] != null) {
                raw = this.recordData[fieldName];
            }
            raw = (raw || '').toString().trim();
            if (!raw) {
                return null;
            }
            return _.filter(_.map(raw.split(','), function (part) {
                return (part || '').trim();
            }), Boolean);
        },

        _iconForValue: function (value) {
            var style = (this.nodeOptions && this.nodeOptions.card_style) || 'theme';
            if (style === 'mode' && MODE_ICONS[value]) {
                return MODE_ICONS[value];
            }
            return THEME_ICON;
        },

        /**
         * Roll Call swatch: stacked squad-number decks + dice (not a loudspeaker).
         */
        _buildRollCallSwatch: function () {
            var $swatch = $('<span class="o_sel_card_swatch o_sel_card_swatch_rollcall"/>');
            var $decks = $('<span class="o_rc_decks" aria-hidden="true"/>');
            _.each(['07', '12', '24'], function (num, idx) {
                $decks.append(
                    $('<span class="o_rc_deck"/>')
                        .addClass('o_rc_deck_' + (idx + 1))
                        .append(
                            $('<span class="o_rc_deck_hash"/>').text('#'),
                            $('<span class="o_rc_deck_num"/>').text(num)
                        )
                );
            });
            var $dice = $('<span class="o_rc_dice" aria-hidden="true"/>').append(
                $('<span class="o_rc_die_dot o_rc_die_tl"/>'),
                $('<span class="o_rc_die_dot o_rc_die_c"/>'),
                $('<span class="o_rc_die_dot o_rc_die_br"/>')
            );
            return $swatch.append($decks, $dice);
        },

        _buildDefaultSwatch: function (value) {
            return $('<span class="o_sel_card_swatch"/>').append(
                $('<span class="o_sel_card_swatch_icon fa"/>').addClass(this._iconForValue(value))
            );
        },

        _renderCards: function (editable) {
            var self = this;
            var style = (this.nodeOptions && this.nodeOptions.card_style) || 'theme';
            this.$el
                .empty()
                .attr('role', 'listbox')
                .toggleClass('o_field_selection_card_mode', style === 'mode')
                .toggleClass('o_field_selection_card_theme', style !== 'mode');

            var allowed = this._getAllowedValues();

            _.each(this.field.selection, function (option) {
                var value = option[0];
                var label = option[1];
                if (!value) {
                    return;
                }

                var selected = value === self.value;
                var locked = !!(allowed && allowed.indexOf(value) === -1);
                var canSelect = editable && !locked;

                var $card = $('<button type="button"/>')
                    .addClass('o_sel_card')
                    .addClass('o_sel_card_' + value)
                    .attr({
                        'data-value': value,
                        'data-locked': locked ? '1' : '0',
                        'role': 'option',
                        'aria-selected': selected ? 'true' : 'false',
                        'aria-disabled': locked ? 'true' : 'false',
                        'tabindex': canSelect ? '0' : '-1',
                        'title': locked
                            ? (label + ' — not included in your plan. Upgrade to unlock.')
                            : label,
                    });

                if (selected) {
                    $card.addClass('o_sel_card_selected');
                }
                if (!editable) {
                    $card.addClass('o_sel_card_readonly').attr('disabled', 'disabled');
                }
                if (locked) {
                    $card.addClass('o_sel_card_locked');
                }

                var $body = $('<span class="o_sel_card_body"/>').append(
                    $('<span class="o_sel_card_name"/>').text(label)
                );
                if (locked) {
                    $body.append(
                        $('<span class="o_sel_card_lock fa fa-lock" aria-hidden="true"/>'),
                        $('<span class="o_sel_card_lock_label"/>').text('Upgrade')
                    );
                } else {
                    $body.append(
                        $('<span class="o_sel_card_check fa fa-check-circle"/>')
                    );
                }

                var $swatch = (style === 'mode' && value === 'linear')
                    ? self._buildRollCallSwatch()
                    : self._buildDefaultSwatch(value);

                $card.append($swatch, $body);
                self.$el.append($card);
            });
        },

        _onCardClick: function (ev) {
            if (this.mode === 'readonly') {
                return;
            }
            var $card = $(ev.currentTarget);
            if ($card.hasClass('o_sel_card_locked') || $card.attr('data-locked') === '1') {
                ev.preventDefault();
                return;
            }
            this._setValue($card.data('value'));
        },

        _onCardKeydown: function (ev) {
            if (this.mode === 'readonly') {
                return;
            }
            var $card = $(ev.currentTarget);
            if ($card.hasClass('o_sel_card_locked') || $card.attr('data-locked') === '1') {
                return;
            }
            if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault();
                this._setValue($card.data('value'));
            }
        },
    });

    fieldRegistry.add('selection_card', SelectionCardWidget);

    return SelectionCardWidget;
});
