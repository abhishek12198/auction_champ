odoo.define('auction_module.sold_sound', function (require) {
    'use strict';

    var AUD = '/auction_module/static/src/audio/';
    var VER = '?v=282m';

    function playClip(src) {
        try {
            var a = new Audio(src + VER);
            a.volume = 1;
            var p = a.play();
            if (p && p.catch) {
                p.catch(function (e) {
                    console.warn('Audio play failed:', e);
                });
            }
            return a;
        } catch (e) {
            console.warn('Audio play failed:', e);
            return null;
        }
    }

    function playSoldSound() {
        playClip(AUD + 'sold_voice.mp3');
        setTimeout(function () {
            playClip(AUD + 'sold_clap.wav');
        }, 420);
    }

    // Expose globally so it can be called from buttons
    window.playSoldSound = playSoldSound;
});
