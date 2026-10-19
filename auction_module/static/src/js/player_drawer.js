/* Lucky Dip Player Drawer — Automatic vs Manual advance on display_auction */
(function (w, d) {
    'use strict';

    var SEAL_HTML =
        '<div class="hud-status-glow" aria-hidden="true"></div>' +
        '<div class="hud-status-seal" id="hudStatusSeal" aria-hidden="true">' +
          '<div class="hud-status-seal-ring"></div>' +
          '<div class="hud-status-seal-ring hud-status-seal-ring--inner"></div>' +
          '<svg class="hud-status-seal-svg" viewBox="0 0 200 200" aria-hidden="true"' +
               ' xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">' +
            '<defs>' +
              '<path id="hudSealArcTop" d="M38,58 A80,80 0 0,1 162,58"/>' +
              '<path id="hudSealArcBot" d="M36,158 A80,80 0 0,0 164,158"/>' +
            '</defs>' +
            '<text id="hudSealArcTopText" fill="currentColor" font-size="18" font-weight="800" letter-spacing="3.8">' +
              '<textPath xlink:href="#hudSealArcTop" href="#hudSealArcTop" startOffset="50%" text-anchor="middle">SOLD TO</textPath>' +
            '</text>' +
            '<text id="hudSealArcBotText" fill="currentColor" font-size="16" font-weight="800" letter-spacing="1.4">' +
              '<textPath xlink:href="#hudSealArcBot" href="#hudSealArcBot" startOffset="50%" text-anchor="middle">TEAM</textPath>' +
            '</text>' +
          '</svg>' +
          '<div class="hud-status-seal-core">' +
            '<img class="hud-status-seal-mark" src="/auction_module/static/img/sold_overlay_gray.png" alt=""/>' +
          '</div>' +
        '</div>';

    function acIsManualPlayerDrawer() {
        return d.body && d.body.getAttribute('data-player-drawer') === 'manual';
    }

    function acPhotoStampHost() {
        return d.querySelector('.hud-photo-col') || (d.getElementById('loadImage') && d.getElementById('loadImage').parentElement);
    }

    function acEnsurePhotoStatus() {
        var overlay = d.getElementById('hudPhotoStatus');
        if (overlay) return overlay;
        var host = acPhotoStampHost();
        if (!host) return null;
        if (w.getComputedStyle(host).position === 'static') {
            host.style.position = 'relative';
        }
        overlay = d.createElement('div');
        overlay.id = 'hudPhotoStatus';
        overlay.className = 'hud-photo-status';
        overlay.setAttribute('data-kind', 'sold');
        overlay.setAttribute('aria-live', 'polite');
        overlay.innerHTML = SEAL_HTML;
        host.appendChild(overlay);
        return overlay;
    }

    function acSetSealArcText(textId, value) {
        var el = d.getElementById(textId);
        if (!el) return;
        var path = el.querySelector('textPath');
        if (path) path.textContent = value || '';
    }

    function acFitSealArcBot(teamNm) {
        var arcBot = d.getElementById('hudSealArcBotText');
        if (!arcBot) return;
        var bp = arcBot.querySelector('textPath');
        if (bp) {
            bp.textContent = teamNm;
            bp.removeAttribute('textLength');
        }
        var pathEl = d.getElementById('hudSealArcBot');
        var usable = 300;
        try {
            if (pathEl && pathEl.getTotalLength) usable = pathEl.getTotalLength() * 0.92;
        } catch (e1) {}
        var len = teamNm.length || 1;
        var fs = 15;
        if (len > 12) fs = 13;
        if (len > 16) fs = 11.5;
        if (len > 20) fs = 10;
        if (len > 26) fs = 8.5;
        if (len > 32) fs = 7.5;
        arcBot.setAttribute('font-size', String(fs));
        arcBot.setAttribute('letter-spacing', len > 18 ? '0' : '0.8');
        if (bp) {
            try {
                var tw = bp.getComputedTextLength ? bp.getComputedTextLength() : 0;
                if (tw > usable || len > 16) {
                    bp.setAttribute('textLength', String(Math.max(80, usable)));
                }
            } catch (e2) {}
        }
    }

    function acClearResultStampOnPhoto() {
        var overlay = d.getElementById('hudPhotoStatus');
        if (overlay) overlay.classList.remove('hud-status-show');
        var banners = d.querySelectorAll('.ac-drawer-result-stamp, .ac-mystery-sold-stamp');
        for (var i = 0; i < banners.length; i++) {
            if (banners[i].parentNode) banners[i].parentNode.removeChild(banners[i]);
        }
    }

    function acShowResultStampOnPhoto(kind, info) {
        var overlay = acEnsurePhotoStatus();
        if (!overlay) return;
        info = info || {};
        var isSold = kind === 'sold';
        overlay.setAttribute('data-kind', isSold ? 'sold' : 'unsold');
        acSetSealArcText('hudSealArcTopText', isSold ? 'SOLD TO' : 'NO BID');
        var teamNm = (isSold && info.team_name) ? String(info.team_name).toUpperCase() : 'UNSOLD';
        acFitSealArcBot(teamNm);
        var logoEl = d.getElementById('hudStatusSealLogo');
        if (logoEl && logoEl.parentNode) {
            logoEl.parentNode.removeChild(logoEl);
        }
        overlay.classList.remove('hud-status-show');
        void overlay.offsetWidth;
        overlay.classList.add('hud-status-show');
    }

    function acMarkWaitingNextPlayer(on) {
        if (!d.body) return;
        d.body.classList.toggle('is-waiting-next', !!on);
        var btns = d.querySelectorAll('.hud-next-btn, .next-player-btn');
        for (var i = 0; i < btns.length; i++) {
            btns[i].classList.toggle('is-waiting-next', !!on);
        }
        if (on && typeof w.acLockAuctionActions === 'function') {
            w.acLockAuctionActions();
        }
    }

    function wrapUnsoldStamp() {
        if (typeof w.showUnsoldStamp !== 'function' || w.showUnsoldStamp._drawerSeal) return;
        w.showUnsoldStamp = function (displaySeconds) {
            acShowResultStampOnPhoto('unsold');
            if (typeof w.acPaintBidHeroResult === 'function') {
                w.acPaintBidHeroResult('unsold');
            }
            if (typeof w.acLockAuctionActions === 'function') {
                w.acLockAuctionActions();
            }
            if (acIsManualPlayerDrawer()) {
                acMarkWaitingNextPlayer(true);
                return;
            }
            var secs = Math.max(1, parseInt(displaySeconds, 10) || 5);
            setTimeout(function () {
                acClearResultStampOnPhoto();
                if (typeof w.changeImage === 'function') w.changeImage(true);
            }, secs * 1000);
        };
        w.showUnsoldStamp._drawerSeal = true;
    }

    function wrapChangeImage() {
        if (typeof w.changeImage !== 'function' || w.changeImage._drawerWrapped) return;
        var original = w.changeImage;
        w.changeImage = function () {
            acClearResultStampOnPhoto();
            acMarkWaitingNextPlayer(false);
            return original.apply(this, arguments);
        };
        w.changeImage._drawerWrapped = true;
    }

    w.acIsManualPlayerDrawer = acIsManualPlayerDrawer;
    w.acShowResultStampOnPhoto = acShowResultStampOnPhoto;
    w.acClearResultStampOnPhoto = acClearResultStampOnPhoto;
    w.acMarkWaitingNextPlayer = acMarkWaitingNextPlayer;

    function bootDrawerWraps() {
        wrapUnsoldStamp();
        wrapChangeImage();
    }
    if (d.readyState === 'loading') {
        d.addEventListener('DOMContentLoaded', bootDrawerWraps);
    } else {
        bootDrawerWraps();
    }
})(window, document);
