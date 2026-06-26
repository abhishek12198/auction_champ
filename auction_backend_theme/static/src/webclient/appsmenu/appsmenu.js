/** @odoo-module **/

import { Dropdown } from "@web/core/dropdown/dropdown";

export class AppsMenu extends Dropdown {
    setup() {
        super.setup();
        this.env.bus.on("ACTION_MANAGER:UI-UPDATED", this, () => this.close());
    }
}

Object.assign(AppsMenu, {
    template: "auction_backend_theme.AppsMenu",
});
