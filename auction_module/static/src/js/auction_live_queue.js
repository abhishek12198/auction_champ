odoo.define('auction_module.auction_live_queue', function (require) {
    "use strict";

    var ajax = require('web.ajax');
    var Longpolling = require('bus.Longpolling');
    var bus = new Longpolling();

    function openPlayerDrawer(playerId) {
        var url = '/auction/player_modal/' + playerId;

        $.get(url, function(htmlContent) {
            // Remove existing drawer if any
            var existingDrawer = document.getElementById('playerDrawer');
            if (existingDrawer) existingDrawer.remove();

            // Create full-screen drawer overlay
            var drawerHtml = `
                <div id="playerDrawer" class="player-drawer-overlay" data-player-id="${playerId}">
                    <div class="player-drawer-backdrop"></div>
                    <div class="player-drawer-container">
                        <div class="player-drawer-header">
                            <button type="button" class="player-drawer-close" onclick="closePlayerDrawer()">
                                <span>&times;</span>
                            </button>
                        </div>
                        <div class="player-drawer-content">
                            ${htmlContent}
                        </div>
                    </div>
                </div>
            `;

            document.body.insertAdjacentHTML('beforeend', drawerHtml);

            // Add CSS styles for drawer (only once)
            if (!document.getElementById('playerDrawerStyles')) {
                var style = document.createElement('style');
                style.id = 'playerDrawerStyles';
                style.textContent = `
                    .player-drawer-overlay {
                        position: fixed;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        z-index: 9999;
                        display: flex;
                        align-items: flex-start;
                        justify-content: flex-end;
                    }

                    .player-drawer-backdrop {
                        position: absolute;
                        top: 0;
                        left: 0;
                        width: 100%;
                        height: 100%;
                        background: rgba(0, 0, 0, 0.5);
                        backdrop-filter: blur(3px);
                        animation: fadeIn 0.3s ease-in-out;
                    }

                    .player-drawer-container {
                        position: relative;
                        width: 90%;
                        height: 100vh;
                        background-image: url('/auction_module/static/src/assets/images/full-bg.png');
                        background-size: cover;
                        background-position: center;
                        box-shadow: -5px 0 25px rgba(0, 0, 0, 0.3);
                        overflow-y: auto;
                        animation: slideInRight 0.4s ease-out;
                        z-index: 10000;
                    }

                    .player-drawer-header {
                        position: sticky;
                        top: 0;
                        background: rgba(0, 0, 0, 0.45);
                        backdrop-filter: blur(6px);
                        padding: 1.5rem;
                        border-bottom: 1px solid #f0f0f0;
                        z-index: 10001;
                    }

                    .player-drawer-close {
                        background: none;
                        border: none;
                        font-size: 3rem;
                        cursor: pointer;
                        color: #fff;
                        padding: 0;
                        width: 50px;
                        height: 50px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: transform 0.2s;
                    }

                    .player-drawer-close:hover {
                        transform: scale(1.2);
                        color: #e53935;
                    }

                    .player-drawer-content {
                        padding: 2rem;
                        min-height: calc(100vh - 80px);
                    }

                    @keyframes fadeIn {
                        from { opacity: 0; }
                        to { opacity: 1; }
                    }

                    @keyframes slideInRight {
                        from { transform: translateX(100%); }
                        to { transform: translateX(0); }
                    }

                    @keyframes slideOutRight {
                        from { transform: translateX(0); }
                        to { transform: translateX(100%); }
                    }

                    @media (max-width: 1024px) {
                        .player-drawer-container { width: 95%; }
                        .player-drawer-content { padding: 1.5rem; }
                    }

                    @media (max-width: 768px) {
                        .player-drawer-container { width: 100%; }
                        .player-drawer-close {
                            font-size: 2.5rem;
                            width: 45px;
                            height: 45px;
                        }.player-drawer-content { padding: 1rem; }
                    }

                    body.drawer-open { overflow: hidden; }
                `;
                document.head.appendChild(style);
            }

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
            }, 300);
        }
    };

    function getCurrentPlayerId() {
        var drawer = document.getElementById('playerDrawer');
        if (drawer) {
            return parseInt(drawer.getAttribute('data-player-id'));
        }
        return null;
    }

    window.setPlayerUnsold = function() {
        if (!confirm('This will set the player to Unsold and later you can bring back to Auction. Click on Ok to continue. Otherwise click on Cancel')) {
            return;
        }

        var playerId = getCurrentPlayerId();

        if (!playerId) {
            alert('Error: Player ID not found');
            return;
        }

        ajax.jsonRpc('/web/dataset/call_kw/auction.team.player/action_unsold', 'call', {
            'model': 'auction.team.player',
            'method': 'action_unsold',
            'args': [[playerId]],
            'kwargs': {}
        }).then(function(result) {
            console.log('Player marked as unsold successfully');
            closePlayerDrawer();
            loadPlayers();
        }).fail(function(error) {
            console.error('Error marking player as unsold:', error);
            alert('Failed to mark player as unsold');
        });
    };

    window.sellPlayerToTeam = function() {
        alert('Implementation pending');
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
                    var button = `<button type="button" class="auction-button" onclick="openPlayerDrawer(${player.id})">${player.serial}</button>`;
                    container.insertAdjacentHTML('beforeend', button);
                });
            }
        }).catch(function(error) {
            console.error('Error loading players:', error);
        });
    }
    window.openPlayerDrawer = openPlayerDrawer;

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