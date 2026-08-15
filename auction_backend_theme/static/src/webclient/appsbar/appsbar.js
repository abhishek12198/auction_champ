/** @odoo-module **/

const { Component } = owl;

export class AppsBar extends Component {
    getAppHref(app) {
        // Never emit action_id=false/undefined — with a Home Action set, Odoo
        // treats incomplete hashes like /web and re-opens the landing page.
        let href = `#menu_id=${app.id}`;
        if (app.actionID) {
            href += `&action_id=${app.actionID}`;
        }
        return href;
    }
}

Object.assign(AppsBar, {
    template: "auction_backend_theme.AppsBar",
    props: {
        apps: Array,
        currentApp: { type: Object, optional: true },
        saasAccountFrozen: { type: Boolean, optional: true },
    },
});
