/** @odoo-module **/

import { titleService } from "@web/core/browser/title_service";
import { session } from "@web/session";

/**
 * Odoo WebClient.setup() always calls setParts({ zopenerp: "Odoo" }).
 * Intercept at the service layer so the tab never flashes "Odoo".
 */
const _origStart = titleService.start.bind(titleService);

titleService.start = function () {
    const service = _origStart();
    const appTitle = session.app_title || "AuctionChamp";
    const _origSetParts = service.setParts.bind(service);
    service.setParts = (parts) => {
        if (parts && Object.prototype.hasOwnProperty.call(parts, "zopenerp")) {
            const val = parts.zopenerp;
            if (!val || val === "Odoo") {
                parts = { ...parts, zopenerp: appTitle };
            }
        }
        return _origSetParts(parts);
    };
    return service;
};
