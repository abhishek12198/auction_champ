/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { session } from "@web/session";

/**
 * Remove the server-rendered boot splash once the Owl webclient is ready.
 * Owl mounts onto document.body with position "self"; without an explicit
 * dismiss the splash can remain as an orphaned overlay above the UI.
 */
function dismissBootSplash() {
    const el = document.getElementById("ac-boot-splash");
    if (el) {
        el.remove();
    }
    const critical = document.getElementById("ac-boot-critical");
    if (critical) {
        critical.remove();
    }
}

patch(WebClient.prototype, "auction_backend_theme.WebClientTitle", {
    setup() {
        this._super(...arguments);
        // Override the "Odoo" title part with the configurable app title from session_info.
        const appTitle = session.app_title || "AuctionChamp";
        this.title.setParts({ zopenerp: appTitle });
        dismissBootSplash();
    },
});
