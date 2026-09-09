/** @odoo-module **/

/**
 * AuctionChamp: keep only Log out in the user menu for now.
 * Other stock Odoo entries (Documentation, Support, Shortcuts, Preferences, …)
 * are removed. New AuctionChamp items can still be registered later.
 */
import { registry } from "@web/core/registry";

const KEEP = new Set(["log_out"]);
const HIDE = new Set([
    "documentation",
    "support",
    "shortcuts",
    "separator",
    "profile",
    "odoo_account",
]);

const menu = registry.category("user_menuitems");

function prune() {
    for (const [name] of menu.getEntries()) {
        if (!KEEP.has(name) && menu.contains(name)) {
            menu.remove(name);
        }
    }
}

prune();

// Prevent stock Odoo entries from being re-added (e.g. by hr Preferences override).
const _add = menu.add.bind(menu);
menu.add = function (name, item, options) {
    if (HIDE.has(name) && !KEEP.has(name)) {
        return menu;
    }
    return _add(name, item, options);
};
