odoo.define('auction_module.sell_toast', function (require) {
    "use strict";

    const AbstractAction = require('web.AbstractAction');
    const core = require('web.core');

    const SellToast = AbstractAction.extend({
    init: function (parent, action) {
        this._super(parent, action);
        this.message = action.params?.message || "Player SOLD";
    },

    start: function () {
        const toast = document.createElement('div');
        toast.className = 'sell-toast';
        toast.innerHTML = this.message;
        document.body.appendChild(toast);

        setTimeout(() => toast.classList.add('fade-out'), 2500);
        setTimeout(() => toast.remove(), 3000);

        return Promise.resolve();
    }
    });

//    const SellToast = AbstractAction.extend({
//        start: function () {
//            console.log(this, "This")
//            const message = "Congratulations ! The player has been sold!";
//
//            const toast = document.createElement('div');
//            toast.className = 'sell-toast';
//            toast.innerHTML = message;
//
//            document.body.appendChild(toast);
//
//            setTimeout(() => {
//                toast.classList.add('fade-out');
//            }, 2500);
//
//            setTimeout(() => {
//                toast.remove();
//            }, 3000);
//
//            return Promise.resolve();
//        }
//    });

    core.action_registry.add('show_sell_toast', SellToast);
});
