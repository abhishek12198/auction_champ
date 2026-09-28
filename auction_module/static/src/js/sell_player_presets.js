odoo.define('auction_module.sell_player_presets', function (require) {
    'use strict';

    /**
     * Quick-select chips in the Sell Player wizard set final_point
     * without a custom field widget.
     */
    function getFinalPointInput($root) {
        var $input = $root.find('.asp-points-box input').filter(':visible').first();
        if (!$input.length) {
            $input = $root.find('input[name="final_point"]').filter(':visible').first();
        }
        return $input;
    }

    function isPointsEditable($input) {
        if (!$input || !$input.length) {
            return false;
        }
        if ($input.prop('disabled') || $input.prop('readonly') || $input.is('[readonly]')) {
            return false;
        }
        if ($input.closest('.o_readonly, .o_field_widget.o_readonly').length) {
            return false;
        }
        // Team must be selected before accepting input
        var $form = $input.closest('.o_asp_wizard, .o_form_view, .modal, .o_dialog');
        var $team = $form.find('input[name="team_id"], select[name="team_id"]').first();
        if ($team.length) {
            var teamVal = ($team.val() || '').toString().trim();
            if (!teamVal || teamVal === 'false' || teamVal === '0') {
                return false;
            }
        }
        return true;
    }

    function setFinalPoint($root, value) {
        var $input = getFinalPointInput($root);
        if (!isPointsEditable($input)) {
            return;
        }
        $input.val(value);
        $input.trigger('input');
        $input.trigger('change');
        // Keep Odoo BasicField in sync when present
        $input.trigger($.Event('keydown', {which: 13, keyCode: 13}));
    }

    $(document).on('click', '.o_asp_wizard .asp-preset-btn', function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        var $btn = $(this);
        var points = parseInt($btn.attr('data-points'), 10);
        if (isNaN(points)) {
            return;
        }
        var $root = $btn.closest('.o_asp_wizard, .modal, .o_dialog, .o_technical_modal');
        if (!$root.length) {
            $root = $(document);
        }
        if (!isPointsEditable(getFinalPointInput($root))) {
            return;
        }
        $root.find('.asp-preset-btn').removeClass('asp-preset-active');
        $btn.addClass('asp-preset-active');
        setFinalPoint($root, points);
    });

    // Block direct edits while points field is locked (no team selected)
    $(document).on(
        'keydown keypress input paste change',
        '.o_asp_wizard .asp-points-box input',
        function (ev) {
            var $input = $(this);
            if (!isPointsEditable($input)) {
                ev.preventDefault();
                ev.stopImmediatePropagation();
                return false;
            }
        }
    );
});
