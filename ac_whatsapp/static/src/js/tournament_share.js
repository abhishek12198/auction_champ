odoo.define('ac_whatsapp.share_tournament', function (require) {
    "use strict";

    var AbstractAction = require('web.AbstractAction');
    var core = require('web.core');

    /**
     * Share tournament invitation on WhatsApp.
     * Tries Web Share API with poster file (mobile), then falls back to
     * text-only share / api.whatsapp.com URL. Poster cannot be attached via
     * wa.me on desktop — user downloads from the wizard instead.
     */
    var ShareTournament = AbstractAction.extend({
        init: function (parent, action) {
            this._super(parent, action);
            var p = (action && action.params) || {};
            this._message = p.message || '';
            this._waUrl = p.wa_url || '';
            this._posterUrl = p.poster_url || '';
            this._title = p.title || 'AuctionChamp';
        },

        start: function () {
            var self = this;
            var msg = this._message;
            var waUrl = this._waUrl;
            var posterUrl = this._posterUrl;
            var title = this._title;

            var openWa = function () {
                if (waUrl) {
                    window.open(waUrl, '_blank');
                }
            };

            var shareTextOnly = function () {
                if (navigator.share) {
                    navigator.share({ title: title, text: msg }).catch(function (err) {
                        if (!err || err.name !== 'AbortError') {
                            openWa();
                        }
                    });
                } else {
                    openWa();
                }
            };

            if (!posterUrl || !navigator.share || !navigator.canShare) {
                shareTextOnly();
                return Promise.resolve();
            }

            return fetch(posterUrl, { credentials: 'same-origin' })
                .then(function (resp) {
                    if (!resp.ok) {
                        throw new Error('poster fetch failed');
                    }
                    return resp.blob();
                })
                .then(function (blob) {
                    var type = blob.type || 'image/jpeg';
                    var ext = type.indexOf('png') >= 0 ? 'png' : 'jpg';
                    var file = new File(
                        [blob],
                        'tournament_poster.' + ext,
                        { type: type }
                    );
                    var payload = { title: title, text: msg, files: [file] };
                    if (navigator.canShare(payload)) {
                        return navigator.share(payload);
                    }
                    shareTextOnly();
                    return null;
                })
                .catch(function () {
                    shareTextOnly();
                })
                .then(function () {
                    return Promise.resolve();
                });
        },
    });

    core.action_registry.add('ac_whatsapp.share_tournament', ShareTournament);
});
