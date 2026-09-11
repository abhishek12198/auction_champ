/** @odoo-module **/

/**
 * AuctionChamp: keep Preferences and Log out in the user menu.
 * Other stock Odoo entries (Documentation, Support, Shortcuts, …) are removed.
 */
import { registry } from "@web/core/registry";

const KEEP = new Set(["profile", "separator", "log_out"]);
const HIDE = new Set([
    "documentation",
    "support",
    "shortcuts",
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
