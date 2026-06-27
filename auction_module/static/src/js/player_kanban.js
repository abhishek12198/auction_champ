odoo.define('auction_module.player_kanban', function () {
    'use strict';

    /**
     * Lightweight photo lightbox for player kanban cards.
     * Called via inline onclick on the .pk2-view-photo button so it works
     * in Odoo 15's legacy kanban (no OWL, no t-on-click).
     */
    window._pk2ShowPhoto = function (btn) {
        var src = btn.getAttribute('data-src');
        var name = btn.getAttribute('data-name') || 'Player Photo';
        if (!src) { return; }

        var overlay = document.createElement('div');
        overlay.className = 'pk2-lightbox';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-label', name);
        overlay.innerHTML =
            '<div class="pk2-lightbox-inner">' +
                '<button class="pk2-lightbox-close" title="Close">&#10005;</button>' +
                '<img src="' + src + '" alt="' + name + '" class="pk2-lightbox-img"/>' +
                '<div class="pk2-lightbox-caption">' + name + '</div>' +
            '</div>';

        // close on backdrop click
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay || e.target.classList.contains('pk2-lightbox-close')) {
                document.body.removeChild(overlay);
            }
        });

        // close on Escape
        var _onKey = function (e) {
            if (e.key === 'Escape') {
                if (document.body.contains(overlay)) {
                    document.body.removeChild(overlay);
                }
                document.removeEventListener('keydown', _onKey);
            }
        };
        document.addEventListener('keydown', _onKey);

        document.body.appendChild(overlay);
        // trigger CSS enter animation
        requestAnimationFrame(function () { overlay.classList.add('pk2-lightbox-open'); });
    };
});
