odoo.define('auction_module.sold_toast_hook', function (require) {
    "use strict";

    const ActionManager = require('web.ActionManager');

    ActionManager.include({
        _handleAction: function (action, options) {
            if (action.context?.show_sell_toast) {
                const message = action.context.toast_message || 'Player SOLD';
                console.log("--------------------------", action)
                const toast = document.createElement('div');
                toast.className = 'sell-toast';
                toast.innerHTML = message;
                document.body.appendChild(toast);

                setTimeout(() => toast.classList.add('fade-out'), 2500);
                setTimeout(() => toast.remove(), 3000);
            }

            return this._super(action, options);
        },
    });
});
