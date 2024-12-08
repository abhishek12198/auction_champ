odoo.define('auction_module.SpacebarReload', function (require) {
    "use strict";

    const core = require('web.core');

    // Add event listener to detect the Spacebar key press
    document.addEventListener('keydown', function (event) {
        console.log("============", event);
        if (event.code === 'Space' || event.key === ' ') {
            // Prevent default action to avoid page scrolling
            event.preventDefault();
            // Reload the browser
            location.reload();
        }
    });
});
