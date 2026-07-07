odoo.define('auction_module.whatsapp_share', function (require) {
    "use strict";

    var AbstractAction = require('web.AbstractAction');
    var core           = require('web.core');

    // ── 1. Share text via native share sheet (mobile) or wa.me (desktop) ─────
    //
    // Called by WhatsappShareWizard.action_share_whatsapp_text().
    // navigator.share({text}) — text-only, no files — works on HTTP and on
    // Android Chrome even after the RPC round-trip because Chrome grants a
    // 5-second user-activation window.  wa.me is the desktop / Safari fallback.

    var ShareText = AbstractAction.extend({

        init: function (parent, action) {
            this._super(parent, action);
            this._message = (action.params && action.params.message) || '';
            this._waUrl   = (action.params && action.params.wa_url)  || '';
        },

        start: function () {
            var msg   = this._message;
            var waUrl = this._waUrl;

            if (navigator.share) {
                navigator.share({ text: msg }).catch(function (err) {
                    if (err && err.name !== 'AbortError') {
                        window.open(waUrl, '_blank');
                    }
                });
            } else {
                window.open(waUrl, '_blank');
            }

            return Promise.resolve();
        },
    });

    core.action_registry.add('auction_module.share_text', ShareText);

    // ── 2. Copy message to clipboard ─────────────────────────────────────────

    var CopyToClipboard = AbstractAction.extend({

        init: function (parent, action) {
            this._super(parent, action);
            this._text = (action.params && action.params.text) || '';
        },

        start: function () {
            var self = this;
            var text = this._text;

            var notify = function (isError, msg) {
                self.do_notify(isError ? 'Copy failed' : 'Copied!', msg, isError);
            };

            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text)
                    .then(function ()  { notify(false, 'Message copied to clipboard.'); })
                    .catch(function () { _fallbackCopy(text, notify); });
            } else {
                _fallbackCopy(text, notify);
            }

            return Promise.resolve();
        },
    });

    function _fallbackCopy(text, notify) {
        try {
            var ta = document.createElement('textarea');
            ta.value = text;
            ta.style.cssText = 'position:fixed;top:-9999px;left:-9999px;opacity:0;';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            notify(false, 'Message copied to clipboard.');
        } catch (e) {
            notify(true, 'Could not copy — please select the text and copy manually.');
        }
    }

    core.action_registry.add('auction_module.copy_to_clipboard', CopyToClipboard);
});


