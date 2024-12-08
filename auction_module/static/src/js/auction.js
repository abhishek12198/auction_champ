odoo.define('auction_module.auction', function (require) {

var ajax = require('web.ajax');
var core = require('web.core');
var Widget = require('web.Widget');
var publicWidget = require('web.public.widget');

var _t = core._t;

// Catch registration form event, because of JS for attendee details
function redirectToURL(url) {
    window.location.href = url;
}
});
