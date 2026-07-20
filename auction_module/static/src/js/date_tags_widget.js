odoo.define('auction_module.DateTagsWidget', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');

    /**
     * DateTagsWidget — many2many_tags-style multi date picker.
     *
     * Stores comma-separated ISO dates on a Char field, e.g.:
     *   "2026-07-20,2026-07-21"
     *
     * Usage:  <field name="tournament_dates" widget="date_tags"/>
     */
    var DateTagsWidget = AbstractField.extend({
        className: 'o_field_date_tags',
        supportedFieldTypes: ['char'],
        tagClass: 'o_date_tag badge badge-pill',

        events: _.extend({}, AbstractField.prototype.events, {
            'change .o_date_tags_picker': '_onDatePicked',
            'click .o_date_tag_remove': '_onRemoveTag',
            'click .o_date_tags_box': '_onBoxClick',
            'keydown .o_date_tags_picker': '_onPickerKeydown',
        }),

        // ── helpers ──────────────────────────────────────────────

        _parseDates: function (value) {
            return _.uniq(
                _.compact(
                    String(value || '')
                        .split(',')
                        .map(function (part) { return part.trim(); })
                )
            ).sort();
        },

        _serializeDates: function (dates) {
            return (_.uniq(dates || []).sort()).join(',');
        },

        _formatLabel: function (iso) {
            if (!iso) {
                return '';
            }
            // Avoid timezone shift: parse as local Y-M-D
            var parts = iso.split('-');
            if (parts.length !== 3) {
                return iso;
            }
            var d = new Date(parseInt(parts[0], 10), parseInt(parts[1], 10) - 1, parseInt(parts[2], 10));
            if (isNaN(d.getTime())) {
                return iso;
            }
            var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                          'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
            var day = ('0' + d.getDate()).slice(-2);
            return day + ' ' + months[d.getMonth()] + ' ' + d.getFullYear();
        },

        _commitDates: function (dates) {
            var serialized = this._serializeDates(dates);
            // Empty string → false so Odoo clears the Char field
            this._setValue(serialized || false);
        },

        // ── render ───────────────────────────────────────────────

        _renderEdit: function () {
            this._renderTags(true);
        },

        _renderReadonly: function () {
            this._renderTags(false);
        },

        _renderTags: function (editable) {
            var self = this;
            var dates = this._parseDates(this.value);

            this.$el.empty();
            var $box = $('<div class="o_date_tags_box"/>');
            if (!editable) {
                $box.addClass('o_date_tags_readonly');
            }

            _.each(dates, function (iso) {
                var $tag = $('<span class="o_date_tag"/>')
                    .attr('data-date', iso)
                    .attr('title', iso);

                $tag.append($('<span class="o_date_tag_text"/>').text(self._formatLabel(iso)));

                if (editable) {
                    $tag.append(
                        $('<button type="button" class="o_date_tag_remove" aria-label="Remove date"/>')
                            .html('&times;')
                    );
                }

                $box.append($tag);
            });

            if (editable) {
                var $picker = $('<input type="date" class="o_date_tags_picker"/>')
                    .attr('title', 'Add a date')
                    .attr('aria-label', 'Add a tournament date');
                $box.append($picker);
            } else if (!dates.length) {
                $box.append($('<span class="text-muted"/>').text('No date set'));
            }

            this.$el.append($box);
        },

        // ── events ───────────────────────────────────────────────

        _onBoxClick: function (ev) {
            if (this.mode === 'readonly') {
                return;
            }
            // Clicking empty area focuses the date picker
            if ($(ev.target).closest('.o_date_tag, .o_date_tags_picker').length) {
                return;
            }
            this.$('.o_date_tags_picker').trigger('focus').trigger('click');
        },

        _onDatePicked: function (ev) {
            var iso = ($(ev.currentTarget).val() || '').trim();
            if (!iso) {
                return;
            }
            var dates = this._parseDates(this.value);
            if (dates.indexOf(iso) === -1) {
                dates.push(iso);
                this._commitDates(dates);
            } else {
                // Already selected — just reset picker so user can pick again
                this.$('.o_date_tags_picker').val('');
            }
        },

        _onRemoveTag: function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            if (this.mode === 'readonly') {
                return;
            }
            var iso = $(ev.currentTarget).closest('.o_date_tag').data('date');
            var dates = _.without(this._parseDates(this.value), iso);
            this._commitDates(dates);
        },

        _onPickerKeydown: function (ev) {
            // Backspace on empty picker removes the last tag (tags-field feel)
            if (ev.key === 'Backspace' && !$(ev.currentTarget).val()) {
                var dates = this._parseDates(this.value);
                if (dates.length) {
                    dates.pop();
                    this._commitDates(dates);
                }
            }
        },
    });

    fieldRegistry.add('date_tags', DateTagsWidget);
    return DateTagsWidget;
});
