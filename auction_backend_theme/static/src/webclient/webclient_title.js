/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { session } from "@web/session";
import { useBus, useEffect } from "@web/core/utils/hooks";

/**
 * Keep the branded splash until the shell has painted, then drop it quickly.
 * Waiting only on the first heavy action left users staring at the splash while
 * tournament kanban / dashboard RPCs finished.
 */
let bootSplashDismissed = false;

function dismissBootSplash() {
    if (bootSplashDismissed) {
        return;
    }
    const el = document.getElementById("ac-boot-splash");
    if (el && el.getAttribute("data-done") === "1") {
        bootSplashDismissed = true;
        return;
    }
    bootSplashDismissed = true;
    if (el) {
        el.setAttribute("data-done", "1");
    }
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
        const appTitle = session.app_title || "AuctionChamp";
        this._super(...arguments);
        this.title.setParts({ zopenerp: appTitle });
        // First action paint — preferred dismiss signal.
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => {
            requestAnimationFrame(() => dismissBootSplash());
        });
        // Also dismiss once the navbar/shell is on screen (systray no longer blocks).
        useEffect(
            () => {
                let tries = 0;
                const tick = () => {
                    tries += 1;
                    if (document.querySelector(".o_main_navbar")) {
                        requestAnimationFrame(() => dismissBootSplash());
                        return;
                    }
                    if (tries < 40) {
                        setTimeout(tick, 50);
                    }
                };
                const start = setTimeout(tick, 120);
                const fallback = setTimeout(dismissBootSplash, 2200);
                return () => {
                    clearTimeout(start);
                    clearTimeout(fallback);
                };
            },
            () => []
        );
    },
});
