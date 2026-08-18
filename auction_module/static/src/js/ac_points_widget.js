odoo.define('auction_module.AcPointsWidget', function (require) {
    'use strict';

    var basicFields = require('web.basic_fields');
    var fieldRegistry = require('web.field_registry');
    var FieldInteger = basicFields.FieldInteger;

    function acUnitName(widget) {
        var data = widget.record && widget.record.data;
        if (data && data.point_unit_name) {
            return data.point_unit_name;
        }
        if (data && data.point_unit_label) {
            return data.point_unit_label;
        }
        var parent = widget.getParent ? widget.getParent() : null;
        var hops = 0;
        while (parent && hops < 12) {
            var pdata = (parent.record && parent.record.data)
                || (parent.state && parent.state.data)
                || null;
            if (pdata && (pdata.point_unit_name || pdata.point_unit_label)) {
                return pdata.point_unit_name || pdata.point_unit_label;
            }
            parent = parent.getParent ? parent.getParent() : null;
            hops += 1;
        }
        if (window.AuctionPointUnit && window.AuctionPointUnit.name) {
            return window.AuctionPointUnit.name();
        }
        return 'Points';
    }

    function acParseInput(widget) {
        var raw;
        if (widget.$input && widget.$input.length) {
            raw = widget.$input.val();
        } else if (widget.$el && widget.$el.is('input')) {
            raw = widget.$el.val();
        } else if (widget.value !== undefined && widget.value !== false) {
            raw = widget.value;
        } else {
            raw = 0;
        }
        var n = parseInt(String(raw).replace(/,/g, ''), 10);
        return isNaN(n) ? 0 : n;
    }

    /**
     * Keep FieldInteger's $el as the <input> so list Tab navigation still
     * treats this as a normal cell. Words are a sibling under the input.
     */
    var FieldAcPoints = FieldInteger.extend({
        className: 'o_field_integer o_field_number o_field_ac_points',

        _renderEdit: function () {
            this._super.apply(this, arguments);
            this._acUpdateWords();
        },

        _renderReadonly: function () {
            this._super.apply(this, arguments);
            this._acUpdateWords();
        },

        _onInput: function () {
            this._super.apply(this, arguments);
            this._acUpdateWords();
        },

        _onChange: function () {
            this._super.apply(this, arguments);
            this._acUpdateWords();
        },

        reset: function () {
            var self = this;
            var def = this._super.apply(this, arguments);
            return Promise.resolve(def).then(function () {
                if (!self.isDestroyed()) {
                    self._acUpdateWords();
                }
            });
        },

        destroy: function () {
            if (this.$el && this.$el.length) {
                this.$el.siblings('.o_ac_points_words').remove();
            }
            this._super.apply(this, arguments);
        },

        _acUpdateWords: function () {
            var self = this;
            if (this.isDestroyed && this.isDestroyed()) {
                return;
            }
            var $parent = this.$el && this.$el.parent();
            if (!$parent || !$parent.length) {
                _.defer(function () {
                    if (!self.isDestroyed()) {
                        self._acUpdateWords();
                    }
                });
                return;
            }
            var $hint = this.$el.next('.o_ac_points_words');
            if (!$hint.length) {
                $hint = $('<div class="o_ac_points_words" aria-live="polite"/>');
                this.$el.after($hint);
            }
            var n = acParseInput(this);
            var unit = acUnitName(this);
            var text = window.AuctionPointUnit && window.AuctionPointUnit.formatWords
                ? window.AuctionPointUnit.formatWords(n, unit)
                : String(n);
            $hint.text(text).toggleClass('o_ac_points_words_empty', !n);
        },
    });

    fieldRegistry.add('ac_points', FieldAcPoints);

    return FieldAcPoints;
});
