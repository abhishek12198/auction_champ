odoo.define('auction_module.revoke_transactions', function (require) {
    'use strict';

    function destValue($wiz) {
        var $checked = $wiz.find('.rt-dest-field input.o_radio_input:checked');
        return ($checked.attr('data-value') || $checked.val() || 'auction');
    }

    function paintToggle($wiz) {
        var value = destValue($wiz) || 'auction';
        $wiz.find('.rt-toggle-btn').removeClass('is-on');
        $wiz.find('.rt-toggle-btn[data-value="' + value + '"]').addClass('is-on');
    }

    $(document).on('click', '.o_rt_wizard .rt-toggle-btn', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var $btn = $(this);
        var value = $btn.attr('data-value') || 'auction';
        var $wiz = $btn.closest('.o_rt_wizard');
        var $radio = $wiz.find('.rt-dest-field input.o_radio_input').filter(function () {
            return ($(this).attr('data-value') || $(this).val()) === value;
        });
        if ($radio.length) {
            $radio.prop('checked', true).trigger('click');
        }
        $wiz.find('.rt-toggle-btn').removeClass('is-on');
        $btn.addClass('is-on');
    });

    $(document).on('change', '.o_rt_wizard .rt-dest-field input.o_radio_input', function () {
        paintToggle($(this).closest('.o_rt_wizard'));
    });

    $(document).on('click', '.o_rt_wizard .rt-card', function (ev) {
        if ($(ev.target).closest('input, a, button').length) {
            return;
        }
        var $checkbox = $(this).find('input[type="checkbox"]');
        if ($checkbox.length) {
            $checkbox.click();
        }
    });

    $(document).on('click', '.o_rt_wizard .rt-warn-accept', function (ev) {
        if ($(ev.target).closest('input').length) {
            return;
        }
        var $checkbox = $(this).find('input[type="checkbox"]');
        if ($checkbox.length) {
            $checkbox.click();
        }
    });
});
