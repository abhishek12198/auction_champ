/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { session } from "@web/session";
import { useBus, useEffect } from "@web/core/utils/hooks";

/**
 * Keep the branded splash until the first action is on screen.
 * Dismissing in setup() left an empty white body for a frame because Owl
 * patches document.body in place (position: "self") after setup().
 */
let bootSplashDismissed = false;

function dismissBootSplash() {
    if (bootSplashDismissed) {
        return;
    }
    bootSplashDismissed = true;
    const el = document.getElementById("ac-boot-splash");
    const finish = () => {
        if (el) {
            el.remove();
        }
        const critical = document.getElementById("ac-boot-critical");
        if (critical) {
            critical.remove();
        }
        document.documentElement.classList.remove("ac-booting");
    };
    if (el) {
        el.classList.add("ac-boot-gone");
        setTimeout(finish, 240);
    } else {
        finish();
    }
}

patch(WebClient.prototype, "auction_backend_theme.WebClientTitle", {
    setup() {
        this._super(...arguments);
        const appTitle = session.app_title || "AuctionChamp";
        this.title.setParts({ zopenerp: appTitle });
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", (mode) => {
            if (mode === "new") {
                return;
            }
            requestAnimationFrame(() => dismissBootSplash());
        });
        useEffect(
            () => {
                const timeout = setTimeout(dismissBootSplash, 4000);
                return () => clearTimeout(timeout);
            },
            () => []
        );
    },
});
