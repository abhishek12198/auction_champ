/** @odoo-module **/

import { Dropdown } from "@web/core/dropdown/dropdown";
import { patch } from "@web/core/utils/patch";

/**
 * Fix: "Cannot read properties of null (reading 'parentElement')"
 *
 * Root cause: a race condition in Odoo core where AppsMenu fires a dropdown
 * state-change event (via EventBus) AFTER the Dropdown component that was
 * listening has already been unmounted — leaving this.el as null. The handler
 * then tries to access this.el.parentElement and throws.
 *
 * Fix: bail out early if the component's root element is already gone.
 */
patch(Dropdown.prototype, "auction_module.dropdown_null_guard", {
    onDropdownStateChanged(payload) {
        if (!this.el || !this.el.parentElement) {
            return;
        }
        return this._super(payload);
    },
});
