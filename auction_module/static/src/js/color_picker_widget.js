odoo.define('auction_module.ColorPickerWidget', function (require) {
    'use strict';

    var AbstractField = require('web.AbstractField');
    var fieldRegistry = require('web.field_registry');

    /**
     * ColorPickerWidget — renders a Char field as an HTML color picker
     * with a companion hex text input.
     * Usage:  <field name="kanban_color" widget="color_picker"/>
     */
    var ColorPickerWidget = AbstractField.extend({
        className: 'o_field_color_picker',
        supportedFieldTypes: ['char'],

        events: {
            'input  .o_cp_native': '_onNativeInput',
            'change .o_cp_text':   '_onTextChange',
        },

        _renderEdit: function () {
            var val = this.value || '#4f46e5';
            this.$el.empty().css({ display: 'inline-flex', alignItems: 'center', gap: '8px' });

            var $native = $('<input type="color" class="o_cp_native">')
                .val(val)
                .css({
                    width: '38px', height: '34px',
                    padding: '2px 3px',
                    border: '1px solid #dee2e6',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    background: 'none',
                });

            var $text = $('<input type="text" class="o_cp_text form-control form-control-sm">')
                .val(val)
                .attr('maxlength', 7)
                .attr('placeholder', '#rrggbb')
                .css({ width: '96px' });

            this.$el.append($native).append($text);
        },

        _renderReadonly: function () {
            var val = this.value || '#4f46e5';
            this.$el.empty().css({ display: 'inline-flex', alignItems: 'center', gap: '6px' });

            var $swatch = $('<span>').css({
                display: 'inline-block',
                width: '18px', height: '18px',
                borderRadius: '4px',
                background: val,
                border: '1px solid rgba(0,0,0,0.15)',
                flexShrink: 0,
            });

            this.$el.append($swatch).append($('<span>').text(val));
        },

        _onNativeInput: function () {
            var val = this.$('.o_cp_native').val();
            this.$('.o_cp_text').val(val);
            this._setValue(val);
        },

        _onTextChange: function () {
            var val = this.$('.o_cp_text').val().trim();
            if (/^#[0-9a-fA-F]{6}$/.test(val)) {
                this.$('.o_cp_native').val(val);
                this._setValue(val);
            }
        },
    });

    fieldRegistry.add('color_picker', ColorPickerWidget);
    return ColorPickerWidget;
});
