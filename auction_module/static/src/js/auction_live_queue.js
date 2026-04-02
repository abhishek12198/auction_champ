odoo.define('auction_module.auction_live_queue', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    var Longpolling = require('bus.Longpolling');
    var bus = new Longpolling();

    function openPlayerDrawer(playerId) {
        var url = '/auction/player_modal/' + playerId;

        // Set player-id on body so openSellModal() / setPlayerUnsold() can read it
        document.body.setAttribute('data-player-id', playerId);

        $.get(url, function(htmlContent) {
            // Remove existing drawer if any
            var existingDrawer = document.getElementById('playerDrawer');
            if (existingDrawer) existingDrawer.remove();

            // Build drawer shell (without content so jQuery can inject + execute scripts)
            var $drawer = $([
                '<div id="playerDrawer" class="player-drawer-overlay" data-player-id="' + playerId + '">',
                '  <div class="player-drawer-backdrop"></div>',
                '  <div class="player-drawer-container">',
                '    <div class="player-drawer-header">',
                '      <button type="button" class="player-drawer-close" onclick="closePlayerDrawer()">',
                '        <span>&times;</span>',
                '      </button>',
                '    </div>',
                '    <div class="player-drawer-content"></div>',
                '  </div>',
                '</div>'
            ].join(''));

            $(document.body).append($drawer);

            // Use jQuery html() so <script> tags inside htmlContent are executed
            $drawer.find('.player-drawer-content').html(htmlContent);

            // Prevent body scrolling
            document.body.classList.add('drawer-open');

            // Close on backdrop click
            document.querySelector('.player-drawer-backdrop').addEventListener('click', closePlayerDrawer);

            // Close on Escape key
            document.addEventListener('keydown', function(e) {
                if (e.key === 'Escape') closePlayerDrawer();
            });
        }).fail(function(error) {
            console.error('Error loading player drawer:', error);
        });
    }

    window.closePlayerDrawer = function() {
        var drawer = document.getElementById('playerDrawer');
        if (drawer) {
            drawer.style.animation = 'slideOutRight 0.3s ease-in forwards';
            setTimeout(function() {
                drawer.remove();
                document.body.classList.remove('drawer-open');
                document.body.removeAttribute('data-player-id');
            }, 300);
        }
    };

    function loadPlayers() {
        ajax.jsonRpc('/auction/get_players_queue', 'call', {}, {
            'context': {'nocache': Math.random()}
        }).then(function (players) {
            var container = document.getElementById("auction_grid");
            if (!container) return;

            container.innerHTML = "";
            if (players && players.length > 0) {
                players.forEach(function (player) {
                    var button = '<button type="button" class="auction-button" onclick="openPlayerDrawer(' + player.id + ')">' + player.serial + '</button>';
                    container.insertAdjacentHTML('beforeend', button);
                });
            }
        }).catch(function(error) {
            console.error('Error loading players:', error);
        });
    }
    window.openPlayerDrawer    = openPlayerDrawer;
    /* Expose so the modal template's changeImage() can reload the grid */
    window._auctionReloadGrid  = loadPlayers;

    bus.on('notification', null, function (notifications) {
        notifications.forEach(function (notification) {
            if (notification[1].type === 'player_queue_update') {
                loadPlayers();
            }
        });
    });

    bus.addChannel('auction_player_update');
    bus.startPolling();

    $(document).ready(function () {
        loadPlayers();
    });
});