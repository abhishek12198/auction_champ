odoo.define('auction_module.SetAuctionRulesWizard', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');
    var FormRenderer = require('web.FormRenderer');

    var SarHtmlWidget = AbstractField.extend({
        className: 'o_field_sar_html',
        supportedFieldTypes: ['html'],

        _render: function () {
            this.$el.html(this.value || '');
        },
    });
    fieldRegistry.add('sar_html', SarHtmlWidget);

    /**
     * Visual helpers for Set Auction Rules: stepper buttons on the three
     * headline metrics. Values still go through the normal input change path.
     */
    FormRenderer.include({
        _renderView: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._sarEnhance();
                setTimeout(function () {
                    self._sarPlaceTeamAdd(self._sarRoot());
                }, 0);
            });
        },

        _sarRoot: function () {
            if (this.$el.hasClass('o_sar_wizard')) {
                return this.$el;
            }
            var $found = this.$el.find('.o_sar_wizard');
            return $found.length ? $found : $();
        },

        _sarEnhance: function () {
            var $root = this._sarRoot();
            if (!$root.length) {
                return;
            }
            this._sarBindSteppers($root);
            this._sarPlaceTeamAdd($root);
        },

        _sarPlaceTeamAdd: function ($root) {
            var $field = $root.find('.sar-team-field').first();
            if (!$field.length) {
                return;
            }
            var $section = $field.closest('.sar-section');
            var $head = $section.find('.sar-section-head').first();
            if (!$head.length) {
                return;
            }
            var $btn = $field.find(
                '.o-kanban-button-new, .o_kanban_button_new, .o_field_x2many_list_row_add'
            ).first();
            if (!$btn.length) {
                return;
            }
            $head.find('.sar-team-add-btn').remove();
            $btn.addClass('sar-team-add-btn');
            $head.append($btn);
        },

        _sarBindSteppers: function ($root) {
            $root.find('.sar-metric').each(function () {
                var $metric = $(this);
                if ($metric.find('.sar-stepper').length) {
                    return;
                }
                var $input = $metric.find('input').first();
                if (!$input.length) {
                    return;
                }
                var step = parseInt($metric.attr('data-step') || '1', 10) || 1;
                var $stepper = $('<div class="sar-stepper"/>');
                var $minus = $('<button type="button" class="sar-stepper-btn" tabindex="-1" title="Decrease"><i class="fa fa-minus"/></button>');
                var $plus = $('<button type="button" class="sar-stepper-btn" tabindex="-1" title="Increase"><i class="fa fa-plus"/></button>');

                function applyDelta(delta) {
                    var raw = parseInt($input.val() || '0', 10);
                    if (isNaN(raw)) {
                        raw = 0;
                    }
                    var next = raw + delta;
                    if (next < 0) {
                        next = 0;
                    }
                    $input.val(next).trigger('input').trigger('change');
                }

                $minus.on('click', function (ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    applyDelta(-step);
                });
                $plus.on('click', function (ev) {
                    ev.preventDefault();
                    ev.stopPropagation();
                    applyDelta(step);
                });

                $stepper.append($plus).append($minus);
                $metric.append($stepper);
            });
        },
    });
});
