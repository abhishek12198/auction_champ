/** @odoo-module **/

import { Dropdown } from "@web/core/dropdown/dropdown";
import { onMounted, onWillUnmount } from "@odoo/owl";

export class AppsMenu extends Dropdown {
    setup() {
        super.setup();
        const closeHandler = () => { this.state.open = false; };
        onMounted(() => this.env.bus.on("ACTION_MANAGER:UI-UPDATED", this, closeHandler));
        onWillUnmount(() => this.env.bus.off("ACTION_MANAGER:UI-UPDATED", this));
    }
}

Object.assign(AppsMenu, {
    template: "auction_backend_theme.AppsMenu",
});
