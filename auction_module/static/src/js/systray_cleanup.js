/** @odoo-module **/

/**
 * AuctionChamp backend: drop mail Messaging (live chat) and Activities
 * from the navbar systray so User Preferences stays visible on mobile.
 */
import { registry } from "@web/core/registry";
import SystrayMenu from "web.SystrayMenu";

const HIDDEN_OWL_SYSTRAY = new Set([
    "mail.MessagingMenu",
    "mail.RtcActivityNotice",
]);

const systray = registry.category("systray");

function removeHiddenOwlItems() {
    HIDDEN_OWL_SYSTRAY.forEach((name) => {
        if (systray.contains(name)) {
            systray.remove(name);
        }
    });
}

removeHiddenOwlItems();

// Mail registers MessagingMenu after the messaging service starts — block those adds.
const _add = systray.add.bind(systray);
systray.add = function (name, item, options) {
    if (HIDDEN_OWL_SYSTRAY.has(name)) {
        return;
    }
    return _add(name, item, options);
};

// Legacy Activity clock menu (mail.systray.ActivityMenu)
if (SystrayMenu && Array.isArray(SystrayMenu.Items)) {
    SystrayMenu.Items = SystrayMenu.Items.filter((Item) => {
        const proto = Item && Item.prototype;
        if (!proto) {
            return true;
        }
        if (proto.template === "mail.systray.ActivityMenu") {
            return false;
        }
        if (proto.name === "activity_menu") {
            return false;
        }
        return true;
    });
}

// If messaging already registered before this module ran, strip again on idle.
Promise.resolve().then(removeHiddenOwlItems);
