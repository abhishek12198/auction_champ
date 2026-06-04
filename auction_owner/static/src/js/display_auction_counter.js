/* ── Enable Counter button handler for /auction/display_auction/ ────────── */
'use strict';

window.ocEnableCounter = function (btn) {
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    btn.textContent = '⏳ Counter Active…';

    fetch('/auction/owner/enable-counter', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: '{}',
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (!data.ok) {
            btn.textContent = '⚠️ No active tournament';
            setTimeout(function () {
                btn.disabled = false;
                btn.textContent = '🔨 Enable Counter';
            }, 3000);
        }
        // Button stays disabled ~4 s then resets so auctioneer cannot double-fire
        setTimeout(function () {
            btn.disabled = false;
            btn.textContent = '🔨 Enable Counter';
        }, 4000);
    })
    .catch(function () {
        btn.disabled = false;
        btn.textContent = '🔨 Enable Counter';
    });
};
