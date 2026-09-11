odoo.define('auction_module.SetAuctionRulesWizard', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var BasicModel = require('web.BasicModel');
    var fieldRegistry = require('web.field_registry');
    var FormRenderer = require('web.FormRenderer');
    var ListRenderer = require('web.ListRenderer');

    var SLAB_INCREMENTS = [25, 50, 100, 250, 500];

    var SarHtmlWidget = AbstractField.extend({
        className: 'o_field_sar_html',
        supportedFieldTypes: ['html'],

        _render: function () {
            this.$el.html(this.value || '');
        },
    });
    fieldRegistry.add('sar_html', SarHtmlWidget);

    function sarFmt(n) {
        n = parseInt(n, 10);
        if (isNaN(n)) {
            n = 0;
        }
        return n.toLocaleString();
    }

    function sarEsc(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function sarRelRecords(value) {
        if (!value) {
            return [];
        }
        if (_.isArray(value.data)) {
            return value.data;
        }
        if (_.isArray(value)) {
            return value;
        }
        return [];
    }

    function sarInt(val) {
        var n = parseInt(val, 10);
        return isNaN(n) ? 0 : n;
    }

    /**
     * Skip the first onchange RPC for bid slabs. New lines only have integers,
     * and From is filled from context — waiting on /onchange was the delay
     * after Enter.
     */
    BasicModel.include({
        generateDefaultValues: function (recordID, options) {
            var self = this;
            return Promise.resolve(this._super.apply(this, arguments)).then(function () {
                var record = self.localData[recordID];
                if (!record || record.model !== 'auction.bid.slab') {
                    return;
                }
                var ctx = record.context || {};
                try {
                    if (record.getContext) {
                        ctx = _.extend({}, ctx, record.getContext() || {});
                    }
                } catch (e) {
                    ctx = record.context || {};
                }
                var fromAmount = sarInt(ctx.default_from_amount);
                if (!fromAmount) {
                    return;
                }
                record._changes = record._changes || {};
                record._changes.from_amount = fromAmount;
                record.data.from_amount = fromAmount;
            });
        },

        _performOnChange: function (record, fields, options) {
            if (record && record.model === 'auction.bid.slab' && options && options.firstOnChange) {
                return Promise.resolve();
            }
            return this._super.apply(this, arguments);
        },
    });

    /**
     * Visual helpers for Set Auction Rules: stepper buttons on the three
     * headline metrics, plus card-style slabs / tier limits. Values still go
     * through the normal x2many change path.
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
            this._sarRenderPreview();
        },

        confirmChange: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function (resetWidgets) {
                if (self._sarRoot().length) {
                    self._sarRenderPreview();
                    self._sarPlaceTeamAdd(self._sarRoot());
                }
                return resetWidgets;
            });
        },

        _sarPreviewChip: function (icon, text, kind) {
            return (
                '<span class="sar-preview-chip sar-chip-' + kind + '">' +
                '<i class="fa ' + icon + '"/> ' + sarEsc(text) + '</span>'
            );
        },

        _sarPreviewSnap: function (amount, slabs) {
            amount = sarInt(amount);
            var sorted = _.sortBy(slabs, function (slab) {
                return -sarInt(slab.data && slab.data.from_amount);
            });
            var i;
            var slab;
            var from;
            var inc;
            var snapped;
            for (i = 0; i < sorted.length; i++) {
                slab = sorted[i];
                from = sarInt(slab.data && slab.data.from_amount);
                if (amount < from) {
                    continue;
                }
                inc = sarInt(slab.data && slab.data.increment);
                if (inc <= 0) {
                    return Math.min(amount, sarInt(slab.data && slab.data.to_amount) || amount);
                }
                snapped = from + Math.floor((amount - from) / inc) * inc;
                snapped = Math.min(snapped, amount);
                if (slab.data && slab.data.to_amount) {
                    snapped = Math.min(snapped, sarInt(slab.data.to_amount));
                }
                return snapped;
            }
            return amount;
        },

        _sarRenderPreview: function () {
            var $root = this._sarRoot();
            if (!$root.length) {
                return;
            }
            var $host = $root.find('.sar-preview-host').first();
            if (!$host.length) {
                return;
            }
            var data = this.state && this.state.data;
            if (!data) {
                return;
            }
            var teams = sarRelRecords(data.team_ids);
            var slabs = sarRelRecords(data.auction_bid_slab_ids);
            var tiers = sarRelRecords(data.tier_limit_ids);
            var nTeams = data.team_ids && data.team_ids.count ? data.team_ids.count : teams.length;
            var chips = [];
            chips.push(this._sarPreviewChip(
                'fa-shield',
                nTeams + ' team' + (nTeams === 1 ? '' : 's'),
                nTeams >= 2 ? 'ok' : 'warn'
            ));
            chips.push(this._sarPreviewChip(
                'fa-list-ol',
                slabs.length + ' slab' + (slabs.length === 1 ? '' : 's'),
                slabs.length ? 'ok' : 'muted'
            ));
            if (tiers.length) {
                chips.push(this._sarPreviewChip(
                    'fa-th-large',
                    tiers.length + ' tier' + (tiers.length === 1 ? '' : 's'),
                    'ok'
                ));
            }
            var purse = sarInt(data.max_points);
            var squad = sarInt(data.max_players);
            var globalBase = sarInt(data.base_point);
            if (purse > 0 && squad > 1) {
                var slots = squad - 1;
                var tierBases = [];
                _.each(tiers, function (tl) {
                    var bid = sarInt(tl.data && tl.data.base_point);
                    if (bid <= 0) {
                        bid = globalBase;
                    }
                    var avail = Math.max(sarInt(tl.data && tl.data.max_players), 0);
                    if (avail) {
                        tierBases.push([bid, avail]);
                    }
                });
                var reserve = 0;
                var left = slots;
                if (tierBases.length) {
                    tierBases.sort(function (a, b) { return a[0] - b[0]; });
                    _.each(tierBases, function (pair) {
                        if (left <= 0) {
                            return;
                        }
                        var take = Math.min(pair[1], left);
                        reserve += take * pair[0];
                        left -= take;
                    });
                    if (left > 0) {
                        reserve += left * tierBases[0][0];
                    }
                } else {
                    reserve = slots * globalBase;
                }
                var snapped = this._sarPreviewSnap(Math.max(purse - reserve, 0), slabs);
                chips.push(this._sarPreviewChip(
                    'fa-calculator',
                    'Budget-safe max ≈ ' + snapped,
                    snapped > 0 ? 'ok' : 'warn'
                ));
            }
            $host.html('<div class="sar-preview">' + chips.join('') + '</div>');
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

    ListRenderer.include({
        _renderView: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._sarDecorateList();
            });
        },

        setRowMode: function (recordID, mode) {
            var self = this;
            var result = this._super.apply(this, arguments);
            if (!this._sarListKind()) {
                return result;
            }
            return Promise.resolve(result).then(function () {
                self._sarDecorateList();
            });
        },

        /**
         * Tab on the last slab cell must open a new slab row, not leave the
         * table for Tier limits.
         */
        _moveToNextLine: function (options) {
            if (this._sarListKind() === 'slabs' && this.editable) {
                options = _.extend({}, options, { forceCreate: true });
            }
            return this._super.apply(this, arguments);
        },

        trigger_up: function (name, info) {
            if (name === 'add_record' && this._sarListKind() === 'slabs') {
                info = info || {};
                info.context = this._sarNextSlabContext(info.context);
            }
            return this._super.apply(this, arguments);
        },

        _sarPrevSlabTo: function () {
            var data = this.state && this.state.data;
            if (!data || !data.length) {
                return 0;
            }
            var prev = data[data.length - 1];
            return sarInt(prev && prev.data && prev.data.to_amount);
        },

        _sarNextSlabContext: function (existing) {
            var extra = { default_from_amount: this._sarPrevSlabTo() };
            if (!existing) {
                return [extra];
            }
            if (_.isArray(existing)) {
                if (!existing.length) {
                    return [extra];
                }
                return _.map(existing, function (ctx) {
                    if (_.isString(ctx)) {
                        try {
                            ctx = JSON.parse(ctx);
                        } catch (e) {
                            ctx = {};
                        }
                    }
                    return _.extend({}, ctx || {}, extra);
                });
            }
            return [_.extend({}, existing, extra)];
        },

        _sarListKind: function () {
            var $wrap = this.$el.parent();
            if (this.$el.closest('.sar-slabs').length || $wrap.hasClass('sar-slabs')) {
                return 'slabs';
            }
            if (this.$el.closest('.o_ac_tier_table').length || $wrap.hasClass('o_ac_tier_table')) {
                return 'tiers';
            }
            return '';
        },

        _sarDecorateList: function () {
            var kind = this._sarListKind();
            if (!kind) {
                return;
            }
            if (kind === 'slabs') {
                this._sarDecorateSlabs();
            } else {
                this._sarDecorateTiers();
            }
        },

        _sarTd: function ($row, name) {
            var idx = -1;
            _.each(this.columns, function (col, i) {
                if (idx === -1 && col.tag === 'field' && col.attrs.name === name) {
                    idx = i;
                }
            });
            if (idx < 0) {
                return $();
            }
            return $row.children('.o_data_cell').eq(idx);
        },

        _sarRecord: function ($row) {
            var id = $row.attr('data-id') || $row.data('id');
            return _.find(this.state.data, function (rec) {
                return rec.id === id;
            });
        },

        _sarNum: function ($row, name) {
            var rec = this._sarRecord($row);
            if (rec && rec.data) {
                var val = rec.data[name];
                var n = parseInt(val, 10);
                return isNaN(n) ? 0 : n;
            }
            return 0;
        },

        _sarSetField: function ($row, fieldName, value) {
            var rec = this._sarRecord($row);
            if (!rec) {
                return;
            }
            if ((rec.data[fieldName] || 0) === value) {
                return;
            }
            var changes = {};
            changes[fieldName] = value;
            this.trigger_up('field_changed', {
                dataPointID: rec.id,
                changes: changes,
            });
        },

        _sarAddStepper: function ($td, step, fieldName) {
            var self = this;
            if (!$td.length || $td.find('.sar-cell-step').length) {
                return;
            }
            var $row = $td.closest('tr');
            var $box = $('<div class="sar-cell-step"/>');
            var $minus = $('<button type="button" class="sar-cell-step-btn" tabindex="-1" title="Decrease"><i class="fa fa-minus"/></button>');
            var $plus = $('<button type="button" class="sar-cell-step-btn" tabindex="-1" title="Increase"><i class="fa fa-plus"/></button>');

            function apply(delta) {
                var next = self._sarNum($row, fieldName) + delta;
                if (next < 0) {
                    next = 0;
                }
                self._sarSetField($row, fieldName, next);
            }

            $minus.on('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                apply(-step);
            });
            $plus.on('click', function (ev) {
                ev.preventDefault();
                ev.stopPropagation();
                apply(step);
            });
            $box.append($plus).append($minus);
            $td.append($box);
        },

        _sarDecorateSlabs: function () {
            var self = this;
            var $rows = this.$el.find('tbody tr.o_data_row');
            $rows.each(function (idx) {
                var $row = $(this);
                $row.addClass('sar-card-row');
                $row.children('.sar-slab-extra').remove();
                var $from = self._sarTd($row, 'from_amount').addClass('sar-cell sar-cell-from');
                var $to = self._sarTd($row, 'to_amount').addClass('sar-cell sar-cell-to');
                var $inc = self._sarTd($row, 'increment').addClass('sar-cell sar-cell-inc');

                if (idx === 0) {
                    $from.removeClass('sar-locked');
                    $from.find('input').prop('readonly', false);
                    self._sarAddStepper($from, 50, 'from_amount');
                } else {
                    $from.addClass('sar-locked');
                    $from.find('input').prop('readonly', true);
                    $from.find('.sar-cell-step').remove();
                }
                self._sarAddStepper($to, 100, 'to_amount');
                self._sarAddStepper($inc, 25, 'increment');

                if (!$inc.find('.sar-slab-chips').length) {
                    var $chips = $('<div class="sar-slab-chips"/>');
                    _.each(SLAB_INCREMENTS, function (n) {
                        var $chip = $('<button type="button" class="sar-inc-chip" tabindex="-1"/>');
                        $chip.attr('data-inc', n).text('+' + n);
                        $chip.on('click', function (ev) {
                            ev.preventDefault();
                            ev.stopPropagation();
                            self._sarSetField($row, 'increment', n);
                        });
                        $chips.append($chip);
                    });
                    $inc.append($chips);
                    $inc.append($('<div class="sar-slab-hint"/>'));
                }
                self._sarRefreshSlabRow($row);
            });
            this._sarLabelAdd(this.$el, 'Add another slab');
        },

        _sarRefreshSlabRow: function ($row) {
            var from = this._sarNum($row, 'from_amount');
            var to = this._sarNum($row, 'to_amount');
            var inc = this._sarNum($row, 'increment');
            var $hint = $row.find('.sar-slab-hint');
            $row.toggleClass('sar-row-warn', Boolean(to && to < from));
            $row.find('.sar-inc-chip').each(function () {
                $(this).toggleClass('is-active', parseInt($(this).attr('data-inc'), 10) === inc);
            });
            if (!to && !inc) {
                $hint.text('Set Until and Increment for this band.');
                return;
            }
            if (to && to < from) {
                $hint.text('Until should be at least ' + sarFmt(from) + '.');
                return;
            }
            if (!inc) {
                $hint.text('Bids from ' + sarFmt(from) + ' to ' + sarFmt(to) + ' — pick an increment.');
                return;
            }
            $hint.text(
                'Bids from ' + sarFmt(from) + ' to ' + sarFmt(to) + ' go up by ' + sarFmt(inc) + '.'
            );
        },

        _sarDecorateTiers: function () {
            var self = this;
            var $rows = this.$el.find('tbody tr.o_data_row');
            $rows.each(function () {
                var $row = $(this);
                $row.removeClass('sar-card-row');
                $row.find('.sar-tier-extra, .sar-cell-step').remove();
                self._sarTd($row, 'tier_id').addClass('sar-tier-name');
                self._sarTd($row, 'max_players').addClass('sar-tier-num');
                var $base = self._sarTd($row, 'base_point').addClass('sar-tier-num');
                var $call = self._sarTd($row, 'max_call').addClass('sar-tier-num');
                $base.toggleClass('sar-hint-global', self._sarNum($row, 'base_point') <= 0);
                $call.toggleClass('sar-hint-uncapped', self._sarNum($row, 'max_call') <= 0);
            });
            this._sarLabelAdd(this.$el, 'Add another tier');
        },

        _sarLabelAdd: function ($list, label) {
            $list.find('.o_field_x2many_list_row_add a').each(function () {
                var $a = $(this);
                if ($a.data('sarLabel') === label) {
                    return;
                }
                $a.data('sarLabel', label);
                $a.text(label);
            });
        },
    });
});
