odoo.define('auction_module.center_toast', function (require) {
    "use strict";

    const notification = require('web.notification');

    const originalNotify = notification.notify;

    // Monkey-patch notify (SAFE in Odoo 15)
    notification.notify = function (params) {
        // Intercept only our custom message
        if (params.title === "AUCTION_SOLD") {
            showCenterToast(params.message);
            return; // ❌ prevent default toast
        }
        return originalNotify.apply(this, arguments);
    };

    function showCenterToast(message) {
        const old = document.querySelector('.auction-center-toast');
        if (old) old.remove();

        const toast = document.createElement('div');
        toast.className = 'auction-center-toast';
        toast.innerHTML = message;

        document.body.appendChild(toast);

        setTimeout(() => toast.classList.add('fade-out'), 2000);
        setTimeout(() => toast.remove(), 2600);
    }
});
