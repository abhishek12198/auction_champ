/** @odoo-module **/

import { patch } from "@web/core/utils/patch";

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
