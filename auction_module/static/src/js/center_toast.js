/** @odoo-module **/

import { registry } from "@web/core/registry";

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

// Service that intercepts notifications with title "AUCTION_SOLD"
// and replaces them with a full-screen center toast.
const centerToastService = {
    dependencies: ["notification"],
    start(env, { notification }) {
        const originalAdd = notification.add.bind(notification);
        notification.add = function (message, options = {}) {
            if (options.title === "AUCTION_SOLD") {
                showCenterToast(message);
                return () => {};
            }
            return originalAdd(message, options);
        };
    },
};

registry.category("services").add("auctionCenterToast", centerToastService);
