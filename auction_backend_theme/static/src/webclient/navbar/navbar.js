/** @odoo-module **/

import { patch } from "@web/core/utils/patch";
import { session } from "@web/session";

import { NavBar } from "@web/webclient/navbar/navbar";
import { AppsMenu } from "@auction_backend_theme/webclient/appsmenu/appsmenu";
import { AppsBar } from "@auction_backend_theme/webclient/appsbar/appsbar";

// Inject our custom component classes so the navbar template can resolve them
patch(NavBar, "auction_backend_theme.NavBar", {
    components: {
        ...NavBar.components,
        AppsMenu,
        AppsBar,
    },
});

// Expose SaaS account expiry warning (set by ac_saas_manager session_info)
// + force full navigation to marketing website from the logo
patch(NavBar.prototype, "auction_backend_theme.NavBar.saasExpiry", {
    setup() {
        this._super(...arguments);
        this.saasExpiryWarning = session.saas_expiry_warning || false;
        this.saasAccountFrozen = Boolean(session.saas_account_frozen);
        if (this.saasAccountFrozen) {
            document.body.classList.add("o_saas_account_frozen");
        }
    },
    /**
     * Leave the backend SPA and open the public website root.
     * Plain href="/" is often intercepted by the webclient router on mobile.
     */
    onWebsiteHomeClick() {
        window.location.assign("/");
    },
});
