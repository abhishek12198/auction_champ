/** @odoo-module **/

const { Component } = owl;

export class AppsBar extends Component {}

Object.assign(AppsBar, {
    template: "auction_backend_theme.AppsBar",
    props: {
        apps: Array,
        currentApp: { type: Object, optional: true },
    },
});
