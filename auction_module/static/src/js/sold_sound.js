odoo.define('auction_module.sold_sound', function (require) {
    'use strict';

    var rpc = require('web.rpc');
    var Dialog = require('web.Dialog');

    // Preload audio
    const soldAudio = new Audio('/auction_module/static/src/audio/congrats.mp3');

    function playSoldSound() {
        soldAudio.currentTime = 0;  // restart sound
        soldAudio.play().catch(function (e) {
            console.warn('Audio play failed:', e);
        });
    }

    // Expose globally so it can be called from buttons
    window.playSoldSound = playSoldSound;
});