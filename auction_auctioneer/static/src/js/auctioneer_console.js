/* ═══════════════════════════════════════════════════════════════════════
   Auctioneer Console – Main JS
   Polls /auction/auctioneer/data and drives the entire UI.
═══════════════════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    /* ── State ──────────────────────────────────────────────────────────── */
    var state = {
        currentPlayer: null,
        teams: [],
        selectedTeam: null,   // team data object for the open modal
        pollTimer: null,
        isLoading: false,
    };

    /* ── Config ─────────────────────────────────────────────────────────── */
    var POLL_INTERVAL = 2500; // ms
    var DATA_URL     = window.AC_DATA_URL     || '/auction/auctioneer/data';
    var BID_URL      = window.AC_BID_URL      || '/auction/auctioneer/place-bid';
    var RESET_URL    = window.AC_RESET_URL    || '/auction/auctioneer/reset-bid';
    var FINALIZE_URL = window.AC_FINALIZE_URL || '/auction/auctioneer/finalize-bid';
    var CSRF         = window.AC_CSRF_TOKEN   || '';

    /* ── Helpers ────────────────────────────────────────────────────────── */
    function fmtPts(n) {
        if (n === null || n === undefined) return '—';
        return Number(n).toLocaleString();
    }

    function showToast(msg, type) {
        var el = document.getElementById('acToast');
        el.textContent = msg;
        el.className = 'ac-toast ac-toast--show ac-toast--' + (type || 'info');
        clearTimeout(el._t);
        el._t = setTimeout(function () {
            el.className = 'ac-toast';
        }, 3500);
    }

    function setStatus(online) {
        var dot  = document.getElementById('acStatusDot');
        var text = document.getElementById('acStatusText');
        if (online) {
            dot.className  = 'ac-status-dot live';
            text.textContent = 'Live';
        } else {
            dot.className  = 'ac-status-dot error';
            text.textContent = 'Reconnecting…';
        }
    }

    /* ── JSON-RPC helper ────────────────────────────────────────────────── */
    function jsonRpc(url, params, callback) {
        var body = JSON.stringify({
            jsonrpc: '2.0',
            method: 'call',
            id: Date.now(),
            params: params || {},
        });
        var xhr = new XMLHttpRequest();
        xhr.open('POST', url, true);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.setRequestHeader('X-CSRFToken', CSRF);
        xhr.onload = function () {
            try {
                var res = JSON.parse(xhr.responseText);
                callback(null, res.result);
            } catch (e) {
                callback(e, null);
            }
        };
        xhr.onerror = function () { callback(new Error('Network error'), null); };
        xhr.send(body);
    }

    /* ── Polling ────────────────────────────────────────────────────────── */
    function poll() {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', DATA_URL + '?_t=' + Date.now(), true);
        xhr.setRequestHeader('X-CSRFToken', CSRF);
        xhr.onload = function () {
            if (xhr.status === 200) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    setStatus(true);
                    render(data);
                } catch (e) {
                    setStatus(false);
                }
            } else {
                setStatus(false);
            }
            scheduleNext();
        };
        xhr.onerror = function () { setStatus(false); scheduleNext(); };
        xhr.send();
    }

    function scheduleNext() {
        clearTimeout(state.pollTimer);
        state.pollTimer = setTimeout(poll, POLL_INTERVAL);
    }

    /* ── Render ─────────────────────────────────────────────────────────── */
    function render(data) {
        state.currentPlayer = data.current_player || null;
        state.teams = data.teams || [];

        renderPlayer(state.currentPlayer);
        renderTeams(state.teams, state.currentPlayer);

        // If modal is open, refresh its next-bid suggestion
        if (state.selectedTeam) {
            var fresh = state.teams.find(function (t) { return t.id === state.selectedTeam.id; });
            if (fresh) {
                state.selectedTeam = fresh;
                refreshModalBid(fresh);
            }
        }
    }

    /* Player panel */
    function renderPlayer(p) {
        var empty = document.getElementById('acPlayerEmpty');
        var card  = document.getElementById('acPlayerCard');

        if (!p) {
            empty.style.display = '';
            card.style.display  = 'none';
            return;
        }

        empty.style.display = 'none';
        card.style.display  = 'flex';

        // Tier
        var tierEl = document.getElementById('acPlayerTier');
        tierEl.textContent = p.tier_name || 'Player';
        tierEl.style.color      = p.tier_color || '#63b3ed';
        tierEl.style.borderColor = p.tier_color || '#63b3ed';
        tierEl.style.background = hexAlpha(p.tier_color || '#63b3ed', 0.12);

        // Photo
        var photo = document.getElementById('acPlayerPhoto');
        photo.src = p.photo_url || '';

        // Sl
        document.getElementById('acPlayerSl').textContent = '#' + (p.sl_no || 0);

        // Name
        document.getElementById('acPlayerName').textContent = p.name || '';

        // Meta
        var parts = [];
        if (p.role) parts.push(p.role);
        if (p.batting_style) parts.push(p.batting_style);
        if (p.bowling_style) parts.push(p.bowling_style);
        document.getElementById('acPlayerMeta').textContent = parts.join(' · ');

        // Base price
        document.getElementById('acBasePrice').textContent = fmtPts(p.base_price);

        // Current bid
        var bidEl = document.getElementById('acCurrentBid');
        if (p.current_bid && p.current_bid > 0) {
            bidEl.textContent = fmtPts(p.current_bid) + ' pts';
        } else {
            bidEl.textContent = '—';
        }

        // Current bidder
        var bidderEl = document.getElementById('acCurrentBidder');
        if (p.current_bid_team) {
            bidderEl.style.display = 'flex';
            var bdLogo = document.getElementById('acBidderLogo');
            var bdName = document.getElementById('acBidderName');
            bdLogo.src = p.current_bid_team.logo_url || '';
            bdName.textContent = p.current_bid_team.name || '';
        } else {
            bidderEl.style.display = 'none';
        }

        // Action buttons
        var hasBid = p.current_bid && p.current_bid > 0;
        document.getElementById('acResetBidBtn').style.display  = hasBid ? '' : 'none';
        document.getElementById('acFinalizeBtn').style.display  = hasBid ? '' : 'none';
    }

    /* Teams grid */
    function renderTeams(teams, player) {
        var grid = document.getElementById('acTeamsGrid');
        var count = document.getElementById('acTeamsCount');
        count.textContent = teams.length + ' team' + (teams.length !== 1 ? 's' : '');

        if (!teams.length) {
            grid.innerHTML = '<p style="color:#64748b;grid-column:1/-1;text-align:center;padding:40px 0;">No teams configured for this tournament.</p>';
            return;
        }

        // Preserve scroll position
        var scrollTop = grid.scrollTop;

        // Build new HTML
        var html = teams.map(function (team) {
            var isActive = player && player.current_bid_team && player.current_bid_team.id === team.id;
            var disabled = !player || !team.can_bid;
            var pct = team.total_points > 0 ? Math.max(0, Math.min(100, (team.remaining_points / team.total_points) * 100)) : 0;
            var barClass = pct > 50 ? '' : pct > 25 ? ' ac-team-purse__bar--mid' : ' ac-team-purse__bar--low';

            var logoHtml = team.logo_url
                ? '<img src="' + team.logo_url + '" alt="' + esc(team.name) + '" class="ac-team-logo" onerror="this.style.display=\'none\'">'
                : '<div class="ac-team-logo-placeholder">🏏</div>';

            var disabledReason = team.can_bid_reason || (!player ? 'No player on stage' : 'Cannot bid');
            var bidLabel = disabled
                ? '<span class="ac-team-no-bid" title="' + esc(disabledReason) + '">🚫 ' + esc(disabledReason) + '</span>'
                : '<span class="ac-team-next-bid">Next: ' + fmtPts(team.next_bid) + ' pts</span>';

            var classes = 'ac-team-btn' + (disabled ? ' ac-team-btn--disabled' : '') + (isActive ? ' ac-team-btn--active' : '');
            var onclick = disabled ? '' : 'onclick="acOpenBidModal(' + team.id + ')"';

            return '<div class="' + classes + '" ' + onclick + ' data-team-id="' + team.id + '">'
                + logoHtml
                + '<span class="ac-team-name">' + esc(team.name) + '</span>'
                + '<div class="ac-team-purse">'
                + '  <div class="ac-team-purse__bar-wrap"><div class="ac-team-purse__bar' + barClass + '" style="width:' + pct.toFixed(1) + '%"></div></div>'
                + '  <div class="ac-team-purse__text"><span class="ac-team-purse__pts">' + fmtPts(team.remaining_points) + '</span> / ' + fmtPts(team.total_points) + ' pts</div>'
                + '</div>'
                + bidLabel
                + '</div>';
        }).join('');

        grid.innerHTML = html;
        grid.scrollTop = scrollTop;
    }

    /* ── Modal ──────────────────────────────────────────────────────────── */
    window.acOpenBidModal = function (teamId) {
        var team   = state.teams.find(function (t) { return t.id === teamId; });
        var player = state.currentPlayer;

        if (!team || !player) return;
        state.selectedTeam = team;

        // Team header
        document.getElementById('acModalTeamLogo').src = team.logo_url || '';
        document.getElementById('acModalTeamName').textContent = team.name || '';
        document.getElementById('acModalTeamMeta').textContent =
            'Remaining: ' + fmtPts(team.remaining_points) + ' pts  |  Max call: ' + fmtPts(team.max_call) + ' pts';

        // Player info
        document.getElementById('acModalPlayerPhoto').src  = player.photo_url || '';
        document.getElementById('acModalPlayerName').textContent  = player.name || '';
        document.getElementById('acModalPlayerRole').textContent  = [player.role, player.batting_style, player.bowling_style].filter(Boolean).join(' · ');
        var tBadge = document.getElementById('acModalTierBadge');
        tBadge.textContent   = player.tier_name || '';
        tBadge.style.color   = player.tier_color || '#63b3ed';
        tBadge.style.borderColor = player.tier_color || '#63b3ed';
        tBadge.style.background  = hexAlpha(player.tier_color || '#63b3ed', 0.1);

        // Bid limits
        document.getElementById('acModalBase').textContent = fmtPts(team.effective_base);
        document.getElementById('acModalMax').textContent  = fmtPts(team.max_call);

        // Pre-fill next bid and validate immediately so the button state is correct on open
        var initialBid = team.next_bid;
        document.getElementById('acBidInput').value = initialBid;
        validateBidInput(team, initialBid);

        document.getElementById('acBidModal').style.display = 'flex';
    };

    window.acCloseBidModal = function (evt) {
        if (evt && evt.target !== document.getElementById('acBidModal')) return;
        document.getElementById('acBidModal').style.display = 'none';
        state.selectedTeam = null;
    };

    function refreshModalBid(team) {
        if (!document.getElementById('acBidModal').style.display || document.getElementById('acBidModal').style.display === 'none') return;
        document.getElementById('acModalTeamMeta').textContent =
            'Remaining: ' + fmtPts(team.remaining_points) + ' pts  |  Max call: ' + fmtPts(team.max_call) + ' pts';
        document.getElementById('acModalBase').textContent = fmtPts(team.effective_base);
        document.getElementById('acModalMax').textContent  = fmtPts(team.max_call);
        // Only update bid input if it hasn't been manually changed
        var cur = parseInt(document.getElementById('acBidInput').value, 10);
        if (!cur || cur === (team.next_bid - (team.effective_base || 0))) {
            document.getElementById('acBidInput').value = team.next_bid;
        }
        // Always re-validate with the current input value against the updated limits
        var currentVal = parseInt(document.getElementById('acBidInput').value, 10) || 0;
        validateBidInput(team, currentVal);
    }

    /* Adjust bid amount by N increments */
    window.acAdjustBid = function (dir) {
        var team = state.selectedTeam;
        if (!team) return;
        var input = document.getElementById('acBidInput');
        var cur   = parseInt(input.value, 10) || team.effective_base;

        // Determine increment from current value using team's slabs
        // We use a fixed step that mirrors the server logic: just show next valid
        // from the data; for manual +/- we increment by the smallest slab step.
        var step = computeStepForAmount(cur, team);
        var next = dir > 0 ? cur + step : Math.max(team.effective_base, cur - step);
        input.value = next;
        validateBidInput(team, next);
    };

    function computeStepForAmount(amount, team) {
        // The team.next_bid was already computed server-side; for manual adjustments
        // we just use the difference between next_bid and current bid as the increment.
        if (!state.currentPlayer) return 1;
        var curBid = state.currentPlayer.current_bid || 0;
        if (curBid > 0 && team.next_bid > curBid) {
            return team.next_bid - curBid;
        }
        return 1;
    }

    function validateBidInput(team, value) {
        var hint = document.getElementById('acBidHint');
        var btn  = document.getElementById('acPlaceBidBtn');
        if (value < team.effective_base) {
            hint.textContent = '⚠ Below base price (' + fmtPts(team.effective_base) + ' pts)';
            btn.disabled = true;
        } else if (value > team.max_call) {
            hint.textContent = '⚠ Exceeds max call (' + fmtPts(team.max_call) + ' pts)';
            btn.disabled = true;
        } else {
            hint.textContent = '';
            btn.disabled = false;
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        var input = document.getElementById('acBidInput');
        if (input) {
            input.addEventListener('input', function () {
                if (state.selectedTeam) {
                    validateBidInput(state.selectedTeam, parseInt(input.value, 10) || 0);
                }
            });
        }

        // Close modal on Escape
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape') acCloseBidModal();
        });
    });

    /* ── Place Bid ──────────────────────────────────────────────────────── */
    window.acPlaceBid = function () {
        var team   = state.selectedTeam;
        var player = state.currentPlayer;
        if (!team || !player) return;

        var bidAmount = parseInt(document.getElementById('acBidInput').value, 10);
        if (!bidAmount || isNaN(bidAmount)) { showToast('Enter a valid bid amount', 'error'); return; }

        var btn = document.getElementById('acPlaceBidBtn');
        btn.disabled = true;
        btn.textContent = 'Placing…';

        jsonRpc(BID_URL, { player_id: player.id, team_id: team.id, bid_amount: bidAmount }, function (err, result) {
            btn.disabled = false;
            btn.textContent = '🔨 PLACE BID';

            if (err || !result) {
                showToast('Network error. Please retry.', 'error');
                return;
            }
            if (!result.success) {
                showToast(result.error || 'Bid failed', 'error');
                return;
            }

            showToast('✅ Bid of ' + fmtPts(result.current_bid) + ' pts placed for ' + result.team_name, 'success');
            // Close modal and force an immediate poll
            document.getElementById('acBidModal').style.display = 'none';
            state.selectedTeam = null;
            clearTimeout(state.pollTimer);
            poll();
        });
    };

    /* ── Reset Bid ──────────────────────────────────────────────────────── */
    window.acResetBid = function () {
        var player = state.currentPlayer;
        if (!player) return;
        if (!confirm('Reset the current bid for ' + player.name + '?')) return;

        jsonRpc(RESET_URL, { player_id: player.id }, function (err, result) {
            if (err || !result || !result.success) {
                showToast('Reset failed', 'error');
                return;
            }
            showToast('Bid reset', 'info');
            clearTimeout(state.pollTimer);
            poll();
        });
    };

    /* ── Finalize Bid (shows confirm modal instead of browser alert) ────── */
    window.acFinalizeBid = function () {
        var player = state.currentPlayer;
        if (!player || !player.current_bid || !player.current_bid_team) {
            showToast('No bid to finalise — place a bid first', 'error');
            return;
        }

        var team = state.teams.find(function (t) { return t.id === player.current_bid_team.id; });

        // Populate confirm-sold modal
        document.getElementById('acSoldPlayerPhoto').src  = player.photo_url || '';
        document.getElementById('acSoldPlayerName').textContent  = player.name || '';
        document.getElementById('acSoldPlayerRole').textContent  =
            [player.role, player.batting_style, player.bowling_style].filter(Boolean).join(' · ');
        var tierEl = document.getElementById('acSoldPlayerTier');
        tierEl.textContent   = player.tier_name || '';
        tierEl.style.color   = player.tier_color || '#63b3ed';
        tierEl.style.borderColor = player.tier_color || '#63b3ed';

        document.getElementById('acSoldTeamLogo').src = player.current_bid_team.logo_url || '';
        document.getElementById('acSoldTeamName').textContent = player.current_bid_team.name || '';
        document.getElementById('acSoldTeamMeta').textContent = team
            ? fmtPts(team.remaining_points - player.current_bid) + ' pts remaining after sale'
            : '';

        document.getElementById('acSoldBidPts').textContent = fmtPts(player.current_bid);

        document.getElementById('acSoldConfirmModal').style.display = 'flex';
    };

    window.acCancelSoldConfirm = function () {
        document.getElementById('acSoldConfirmModal').style.display = 'none';
    };

    window.acConfirmSold = function () {
        var player = state.currentPlayer;
        if (!player) return;

        var bidder = player.current_bid_team ? player.current_bid_team.name : '?';
        var confirmBtn = document.getElementById('acSoldConfirmBtn');
        var soldBtn    = document.getElementById('acFinalizeBtn');

        confirmBtn.disabled = true;
        confirmBtn.textContent = '⏳ Processing…';

        jsonRpc(FINALIZE_URL, { player_id: player.id }, function (err, result) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = '🏆 CONFIRM SOLD!';

            if (err || !result) {
                showToast('Network error during finalization', 'error');
                return;
            }
            if (!result.success) {
                showToast(result.error || 'Finalization failed', 'error');
                return;
            }

            // Close confirm modal
            document.getElementById('acSoldConfirmModal').style.display = 'none';

            showToast('🎉 ' + player.name + ' SOLD to ' + bidder + ' for ' + fmtPts(player.current_bid) + ' pts!', 'success');

            // Signal the display_auction page (open in any tab) to advance to next player
            try {
                localStorage.setItem('auction:player_sold', JSON.stringify({
                    ts: Date.now(),
                    player: player.name,
                    team: bidder,
                    pts: player.current_bid,
                }));
            } catch (e) { /* storage not available — ignore */ }

            clearTimeout(state.pollTimer);
            poll();
        });
    };

    /* ── Utility ────────────────────────────────────────────────────────── */
    function esc(str) {
        return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function hexAlpha(hex, alpha) {
        hex = (hex || '#cccccc').replace('#', '');
        if (hex.length === 3) hex = hex[0]+hex[0]+hex[1]+hex[1]+hex[2]+hex[2];
        var r = parseInt(hex.slice(0,2),16), g = parseInt(hex.slice(2,4),16), b = parseInt(hex.slice(4,6),16);
        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
    }

    /* ── Boot ───────────────────────────────────────────────────────────── */
    document.addEventListener('DOMContentLoaded', function () {
        poll();
    });

})();
