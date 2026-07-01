/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { WebClient } from "@web/webclient/webclient";
import { session } from "@web/session";

patch(WebClient.prototype, "auction_backend_theme.WebClientTitle", {
    setup() {
        this._super(...arguments);
        // Override the "Odoo" title part with the configurable app title from session_info.
        const appTitle = session.app_title || "AuctionChamp";
        this.title.setParts({ zopenerp: appTitle });
    },
});
