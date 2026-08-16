odoo.define('auction_module.PlayerRegisterFlash', function (require) {
    'use strict';

    var FormRenderer = require('web.FormRenderer');

    FormRenderer.include({
        _renderView: function () {
            var self = this;
            return this._super.apply(this, arguments).then(function () {
                self._aprShowFlash();
            });
        },

        _aprShowFlash: function () {
            var $stats = this.$el.find('.o_tourn_player_stats');
            if (!$stats.length) {
                return;
            }
            var ctx = (this.state && this.state.context) || {};
            var msg = ctx.player_register_flash;
            if (!msg) {
                return;
            }
            $stats.find('.o_tps_flash').remove();
            var $flash = $('<div class="o_tps_flash" role="status"/>').text(msg);
            $stats.prepend($flash);
            setTimeout(function () {
                $flash.addClass('o_tps_flash-out');
            }, 2500);
            setTimeout(function () {
                $flash.remove();
            }, 3200);
        },
    });
});
