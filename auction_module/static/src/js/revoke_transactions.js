odoo.define('auction_module.revoke_transactions', function (require) {
    'use strict';

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
