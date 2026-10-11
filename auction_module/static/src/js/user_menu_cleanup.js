/** @odoo-module **/

/**
 * AuctionChamp user menu: User Manual, Preferences, and Log out.
 * Other stock Odoo entries (Documentation, Support, Shortcuts, …) are removed.
 */
import { browser } from "@web/core/browser/browser";
import { registry } from "@web/core/registry";

const KEEP = new Set(["user_manual", "profile", "separator", "log_out"]);
const HIDE = new Set([
    "documentation",
    "support",
    "shortcuts",
    "odoo_account",
]);

const menu = registry.category("user_menuitems");

function userManualItem(env) {
    const url = "/user-manual";
    return {
        type: "item",
        id: "user_manual",
        description: env._t("User Manual"),
        href: url,
        callback: () => {
            browser.open(url, "_blank");
        },
        // Just above Preferences (50) and Log out (70).
        sequence: 45,
    };
}

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

menu.add("user_manual", userManualItem);
