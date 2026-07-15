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
        slabs: [],            // bid slabs sorted descending by from_amount
        players: [],          // showcase pool
        remainingCount: 0,
        showcaseMode: window.AC_SHOWCASE_MODE || 'manual',
        selectedTeam: null,   // team data object for the open modal
        tournamentType: window.AC_SPORT || 'cricket',
        pollTimer: null,
        isLoading: false,
        diceRolling: false,
        dicePicked: null,     // {id, sl_no, is_mystery}
        diceTimer: null,
        nextBusy: false,
        callBusy: false,
        revealBusy: false,
    };

    /* ── Config ─────────────────────────────────────────────────────────── */
    var POLL_INTERVAL = 2500; // ms
    var DATA_URL     = window.AC_DATA_URL     || '/auction/auctioneer/data';
    var BID_URL      = window.AC_BID_URL      || '/auction/auctioneer/place-bid';
    var RESET_URL    = window.AC_RESET_URL    || '/auction/auctioneer/reset-bid';
    var FINALIZE_URL = window.AC_FINALIZE_URL || '/auction/auctioneer/finalize-bid';
    var DICE_URL     = window.AC_DICE_URL     || '/auction/auctioneer/dice';
    var CALL_URL     = window.AC_CALL_URL     || '/auction/auctioneer/call-player';
    var NEXT_URL     = window.AC_NEXT_URL     || '/auction/auctioneer/next-player';
    var REVEAL_URL   = window.AC_REVEAL_URL   || '/auction/auctioneer/reveal-mystery';
    var CSRF         = window.AC_CSRF_TOKEN   || '';
    var DEFAULT_PHOTO = '/auction_module/static/img/default_icon.png';

    function isMysteryHidden(p) {
        return !!(p && p.is_mystery && !p.mystery_revealed);
    }

    function isAwaitingReveal(p) {
        p = p || state.currentPlayer;
        return !!(p && (p.awaiting_reveal || (p.is_mystery && !p.mystery_revealed && p.state === 'sold')));
    }

    function gateShowcase(actionLabel) {
        if (!isAwaitingReveal()) return false;
        showToast('Reveal the mystery player before ' + (actionLabel || 'continuing'), 'error');
        return true;
    }

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
        var pill = document.getElementById('acLiveIndicator');
        if (online) {
            dot.className  = 'ac-live-pill__dot is-live';
            if (pill) pill.className = 'ac-live-pill is-live';
            text.textContent = 'Live';
        } else {
            dot.className  = 'ac-live-pill__dot is-error';
            if (pill) pill.className = 'ac-live-pill is-error';
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

    function isFootball(p) {
        var t = (p && p.tournament_type) || state.tournamentType || 'cricket';
        return t === 'football';
    }

    function sportIcon() {
        return isFootball() ? '⚽' : '🏏';
    }

    function attrChip(label, value) {
        if (!value) return '';
        return '<div class="ac-attr-chip">'
            + '<span class="ac-attr-chip__label">' + esc(label) + '</span>'
            + '<span class="ac-attr-chip__value">' + esc(String(value)) + '</span>'
            + '</div>';
    }

    function playerAttrChipsHtml(p) {
        if (!p) return '';
        var chips = [];
        if (isFootball(p)) {
            if (p.use_other_attributes && p.other_attributes && p.other_attributes.length) {
                p.other_attributes.forEach(function (a) {
                    chips.push(attrChip(a.label, a.value));
                });
            } else {
                chips.push(attrChip('Position', p.dominant_position || p.dominant_position_code));
                chips.push(attrChip('Foot', p.preferred_foot));
                chips.push(attrChip('Age', p.age));
                if (p.p_category) chips.push(attrChip('Category', p.p_category));
                if (p.secondary_positions && p.secondary_positions.length) {
                    chips.push(attrChip('Secondary', p.secondary_positions.join(', ')));
                }
            }
        } else {
            chips.push(attrChip('Role', p.role));
            chips.push(attrChip('Bat', p.batting_style));
            chips.push(attrChip('Bowl', p.bowling_style));
        }
        return chips.filter(Boolean).join('');
    }

    function playerMetaLine(p) {
        if (!p) return '';
        if (isFootball(p)) {
            if (p.use_other_attributes && p.other_attributes && p.other_attributes.length) {
                return p.other_attributes.map(function (a) {
                    return a.value;
                }).filter(Boolean).join(' · ');
            }
            return [p.dominant_position || p.dominant_position_code, p.preferred_foot, p.age ? ('Age ' + p.age) : '']
                .filter(Boolean).join(' · ');
        }
        return [p.role, p.batting_style, p.bowling_style].filter(Boolean).join(' · ');
    }

    /* ── Render ─────────────────────────────────────────────────────────── */
    function render(data) {
        state.currentPlayer = data.current_player || null;
        state.teams = data.teams || [];
        state.slabs = data.slabs || [];
        state.players = data.players || [];
        state.remainingCount = data.remaining_count || 0;
        if (data.tournament && data.tournament.tournament_type) {
            state.tournamentType = data.tournament.tournament_type;
            document.getElementById('acBody').setAttribute('data-sport', state.tournamentType);
            var emptyIcon = document.getElementById('acEmptyIcon');
            if (emptyIcon) emptyIcon.textContent = sportIcon();
        }
        if (data.tournament && data.tournament.showcase_mode) {
            state.showcaseMode = data.tournament.showcase_mode;
        }

        renderShowcase();
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

        // Keep number pad fresh while open
        var pad = document.getElementById('acNumberPad');
        if (pad && pad.style.display !== 'none') {
            renderNumberPad();
        }
    }

    /* ── Showcase (manual / random) ─────────────────────────────────────── */
    function renderShowcase() {
        var mode = state.showcaseMode === 'random' ? 'random' : 'manual';
        var modeEl = document.getElementById('acShowcaseMode');
        var manualEl = document.getElementById('acShowcaseManual');
        var randomEl = document.getElementById('acShowcaseRandom');
        var emptySub = document.getElementById('acEmptySub');
        var remainEl = document.getElementById('acRemainCount');

        if (modeEl) {
            modeEl.textContent = mode === 'random' ? 'Random' : 'Manual';
            modeEl.className = 'ac-showcase__mode ac-showcase__mode--' + mode;
        }
        if (manualEl) manualEl.style.display = mode === 'manual' ? 'flex' : 'none';
        if (randomEl) randomEl.style.display = mode === 'random' ? 'flex' : 'none';
        if (remainEl) {
            remainEl.textContent = state.remainingCount
                ? (state.remainingCount + ' left')
                : 'Pool empty';
        }
        if (emptySub) {
            if (isAwaitingReveal()) {
                emptySub.textContent = 'Reveal the mystery player before calling the next one';
            } else {
                emptySub.textContent = mode === 'random'
                    ? 'Tap Next Player to bring someone onto stage & projector'
                    : 'Roll the dice or pick a number to call a player onto stage';
            }
        }

        var locked = isAwaitingReveal();
        var diceBtn = document.getElementById('acDiceBtn');
        var numsBtn = document.getElementById('acNumbersBtn');
        var nextBtn = document.getElementById('acNextBtn');
        if (diceBtn && !state.diceRolling) diceBtn.disabled = locked;
        if (numsBtn) numsBtn.disabled = locked;
        if (nextBtn && !state.nextBusy) nextBtn.disabled = locked;

        // Dice result strip visibility
        var diceStrip = document.getElementById('acDiceResult');
        if (diceStrip && !state.diceRolling) {
            if (state.dicePicked && mode === 'manual' && !locked) {
                diceStrip.style.display = 'flex';
                var numEl = document.getElementById('acDiceResultNum');
                if (numEl) {
                    numEl.textContent = state.dicePicked.is_mystery
                        ? '?'
                        : ('#' + (state.dicePicked.sl_no || '—'));
                }
            } else if (!state.dicePicked || locked) {
                diceStrip.style.display = 'none';
            }
        }
        syncDiceFab();
    }

    function syncDiceFab() {
        var fab = document.getElementById('acDiceFab');
        if (!fab) return;
        var mode = state.showcaseMode === 'random' ? 'random' : 'manual';
        var isMobile = window.matchMedia('(max-width: 900px)').matches;
        var show = isMobile && mode === 'manual' && !isAwaitingReveal();
        fab.style.display = show ? 'flex' : 'none';
        fab.classList.toggle('is-rolling', !!state.diceRolling);
        fab.classList.toggle('has-result', !!(state.dicePicked && !state.diceRolling));
        var numEl = document.getElementById('acDiceFabNum');
        var lbl = document.getElementById('acDiceFabLabel');
        if (state.diceRolling) {
            if (numEl) numEl.textContent = '';
            if (lbl) lbl.textContent = 'Rolling…';
        } else if (state.dicePicked) {
            if (numEl) {
                numEl.textContent = state.dicePicked.is_mystery
                    ? '?'
                    : ('#' + (state.dicePicked.sl_no || '—'));
            }
            if (lbl) lbl.textContent = 'Tap to Call';
        } else {
            if (numEl) numEl.textContent = '';
            if (lbl) lbl.textContent = 'Roll Dice';
        }
    }

    window.acOnDiceFabTap = function () {
        if (state.dicePicked && !state.diceRolling) {
            acCallDicePlayer();
            return;
        }
        acRollDice();
    };

    function setDiceButtonRolling(on) {
        var btn = document.getElementById('acDiceBtn');
        var lbl = document.getElementById('acDiceBtnLabel');
        if (btn) {
            btn.disabled = !!on || isAwaitingReveal();
            btn.classList.toggle('is-rolling', !!on);
        }
        if (lbl) lbl.textContent = on ? 'Rolling…' : (state.dicePicked ? 'Roll Again' : 'Roll Dice');
        syncDiceFab();
    }

    function broadcastDice(dState, number, playerId, cb) {
        if (typeof playerId === 'function') {
            cb = playerId;
            playerId = false;
        }
        jsonRpc(DICE_URL, {
            state: dState,
            number: number || 0,
            player_id: playerId || false,
        }, function (err, result) {
            if (cb) cb(err, result);
        });
    }

    window.acRollDice = function () {
        if (state.showcaseMode !== 'manual' || state.diceRolling) return;
        if (gateShowcase('rolling the dice')) return;

        var available = (state.players || []).filter(function (p) {
            return p && p.state === 'auction';
        });
        if (!available.length) {
            showToast('No players left to roll', 'error');
            return;
        }

        if (state.diceTimer) {
            clearTimeout(state.diceTimer);
            state.diceTimer = null;
        }

        var picked = available[Math.floor(Math.random() * available.length)];
        state.dicePicked = null;
        state.diceRolling = true;
        setDiceButtonRolling(true);
        document.getElementById('acDiceResult').style.display = 'none';

        broadcastDice('rolling', 0, false);

        var rollCount = 0;
        var maxRolls = 22;
        var resultBroadcast = false;
        var rollInt = setInterval(function () {
            rollCount++;
            if (rollCount === 10 && !resultBroadcast) {
                resultBroadcast = true;
                // Server resolves serial + mystery mask from player_id
                broadcastDice('result', 0, picked.id);
            }
            if (rollCount >= maxRolls) {
                clearInterval(rollInt);
                state.diceRolling = false;
                state.dicePicked = {
                    id: picked.id,
                    sl_no: picked.is_mystery ? 0 : (picked.sl_no || 0),
                    is_mystery: !!picked.is_mystery,
                };
                setDiceButtonRolling(false);
                renderShowcase();
                if (!resultBroadcast) {
                    broadcastDice('result', 0, picked.id);
                }
                state.diceTimer = setTimeout(function () {
                    broadcastDice('idle', 0, false);
                    state.diceTimer = null;
                }, 7000);
            }
        }, 100);
    };

    window.acCallDicePlayer = function () {
        if (gateShowcase('calling a player')) return;
        if (!state.dicePicked || !state.dicePicked.id) return;
        acCallPlayer(state.dicePicked.id);
    };

    window.acOpenNumberPad = function () {
        if (gateShowcase('selecting a player')) return;
        var pad = document.getElementById('acNumberPad');
        if (!pad) return;
        var search = document.getElementById('acNumpadSearch');
        if (search) search.value = '';
        renderNumberPad();
        pad.style.display = 'flex';
    };

    window.acCloseNumberPad = function (ev) {
        // Overlay click only when the backdrop itself is the target
        if (ev && ev.type === 'click' && ev.target && ev.target.id && ev.target.id !== 'acNumberPad') {
            return;
        }
        var pad = document.getElementById('acNumberPad');
        if (pad) pad.style.display = 'none';
    };

    window.acFilterNumberPad = function () {
        renderNumberPad();
    };

    function renderNumberPad() {
        var grid = document.getElementById('acNumpadGrid');
        if (!grid) return;
        var q = ((document.getElementById('acNumpadSearch') || {}).value || '').trim().toLowerCase();
        var html = '';
        var list = state.players || [];
        if (!list.length) {
            grid.innerHTML = '<div class="ac-numpad__empty">No players in this tournament</div>';
            return;
        }
        list.forEach(function (p) {
            // Always treat mystery as locked in the selector until revealed
            var mystery = !!p.is_mystery && !p.mystery_revealed;
            var numLabel = mystery ? '?' : String(p.sl_no || '—');
            var nameLabel = mystery ? 'Mystery' : (p.name || '');
            var label = mystery ? '?' : ('#' + (p.sl_no || '—'));
            // Mystery: searchable only by ? — never by real name/serial
            var hay = (label + ' ' + numLabel + ' ' + nameLabel).toLowerCase();
            if (q && hay.indexOf(q) === -1) return;
            var st = p.state || 'auction';
            var disabled = st !== 'auction';
            var cls = 'ac-numpad__btn'
                + (disabled ? ' is-disabled is-' + st : '')
                + (mystery ? ' is-mystery' : '')
                + (state.dicePicked && state.dicePicked.id === p.id ? ' is-dice' : '')
                + (state.currentPlayer && state.currentPlayer.id === p.id ? ' is-onstage' : '');
            html += '<button type="button" class="' + cls + '"'
                + (disabled ? ' disabled' : ' onclick="acCallPlayer(' + p.id + ')"')
                + ' title="' + esc(mystery ? 'Mystery Player' : (p.name || '')) + '">'
                + '<span class="ac-numpad__num">' + esc(numLabel) + '</span>'
                + '<span class="ac-numpad__name">' + esc(nameLabel) + '</span>'
                + (disabled ? '<span class="ac-numpad__state">' + esc(st) + '</span>' : '')
                + '</button>';
        });
        grid.innerHTML = html || '<div class="ac-numpad__empty">No matches</div>';
    }

    window.acCallPlayer = function (playerId) {
        if (gateShowcase('calling a player')) return;
        if (state.callBusy) return;
        state.callBusy = true;
        jsonRpc(CALL_URL, { player_id: playerId }, function (err, result) {
            state.callBusy = false;
            if (err || !result) {
                showToast('Network error calling player', 'error');
                return;
            }
            if (!result.success) {
                showToast(result.error || 'Could not call player', 'error');
                return;
            }
            state.dicePicked = null;
            document.getElementById('acDiceResult').style.display = 'none';
            setDiceButtonRolling(false);
            acCloseNumberPad();
            var label = result.is_mystery
                ? 'Mystery Player'
                : ('#' + (result.sl_no || '') + ' ' + (result.name || ''));
            showToast('On stage: ' + label, 'success');
            clearTimeout(state.pollTimer);
            poll();
        });
    };

    window.acNextPlayer = function () {
        if (state.showcaseMode !== 'random' || state.nextBusy) return;
        if (gateShowcase('calling the next player')) return;
        state.nextBusy = true;
        var btn = document.getElementById('acNextBtn');
        if (btn) btn.disabled = true;
        jsonRpc(NEXT_URL, {}, function (err, result) {
            state.nextBusy = false;
            if (btn) btn.disabled = isAwaitingReveal();
            if (err || !result) {
                showToast('Network error loading next player', 'error');
                return;
            }
            if (!result.success) {
                showToast(result.error || 'No players left', 'error');
                return;
            }
            var label = result.is_mystery
                ? 'Mystery Player'
                : ('#' + (result.sl_no || '') + ' ' + (result.name || ''));
            showToast('Next: ' + label, 'success');
            clearTimeout(state.pollTimer);
            poll();
        });
    };

    /* Player panel */
    function renderPlayer(p) {
        var empty = document.getElementById('acPlayerEmpty');
        var card  = document.getElementById('acPlayerCard');
        var cardRoot = card;

        if (!p) {
            empty.style.display = '';
            card.style.display  = 'none';
            if (cardRoot) cardRoot.classList.remove('is-mystery-locked', 'is-awaiting-reveal');
            var revealBtn0 = document.getElementById('acRevealBtn');
            if (revealBtn0) revealBtn0.style.display = 'none';
            return;
        }

        empty.style.display = 'none';
        card.style.display  = 'flex';

        var hidden = isMysteryHidden(p);
        var awaiting = isAwaitingReveal(p);
        if (cardRoot) {
            cardRoot.classList.toggle('is-mystery-locked', hidden);
            cardRoot.classList.toggle('is-awaiting-reveal', awaiting);
        }

        // Tier
        var tierEl = document.getElementById('acPlayerTier');
        if (hidden) {
            tierEl.textContent = 'Mystery';
            tierEl.style.color = '#c084fc';
            tierEl.style.borderColor = '#c084fc';
            tierEl.style.background = hexAlpha('#c084fc', 0.12);
        } else {
            tierEl.textContent = p.tier_name || 'Player';
            tierEl.style.color      = p.tier_color || '#e0b84a';
            tierEl.style.borderColor = p.tier_color || '#e0b84a';
            tierEl.style.background = hexAlpha(p.tier_color || '#e0b84a', 0.12);
        }

        // Photo
        var photo = document.getElementById('acPlayerPhoto');
        photo.src = hidden ? DEFAULT_PHOTO : (p.photo_url || DEFAULT_PHOTO);
        photo.style.filter = hidden ? 'grayscale(1) brightness(0.72)' : '';

        // Sl
        document.getElementById('acPlayerSl').textContent = hidden
            ? '?'
            : ('#' + (p.sl_no || 0));

        // Name
        document.getElementById('acPlayerName').textContent = hidden
            ? 'Mystery Player'
            : (p.name || '');

        // Sport-aware attribute chips
        var attrsEl = document.getElementById('acPlayerAttrs');
        if (attrsEl) {
            attrsEl.innerHTML = hidden ? '' : playerAttrChipsHtml(p);
        } else {
            document.getElementById('acPlayerMeta').textContent = hidden ? '' : playerMetaLine(p);
        }

        // Base / sold price
        if (awaiting && p.sold_points) {
            document.getElementById('acBasePrice').textContent = fmtPts(p.sold_points);
            document.getElementById('acCurrentBid').textContent = 'SOLD';
        } else {
            document.getElementById('acBasePrice').textContent = fmtPts(p.base_price);
            var bidEl = document.getElementById('acCurrentBid');
            if (p.current_bid && p.current_bid > 0) {
                bidEl.textContent = fmtPts(p.current_bid) + ' pts';
            } else {
                bidEl.textContent = '—';
            }
        }

        // Current bidder / winning team
        var bidderEl = document.getElementById('acCurrentBidder');
        if (p.current_bid_team) {
            bidderEl.style.display = 'flex';
            var bdLogo = document.getElementById('acBidderLogo');
            var bdName = document.getElementById('acBidderName');
            bdLogo.src = p.current_bid_team.logo_url || '';
            bdName.textContent = p.current_bid_team.name || '';
            var bdLabel = bidderEl.querySelector('.ac-bidder-label');
            if (bdLabel) bdLabel.textContent = awaiting ? 'Sold To' : 'Highest Bid';
        } else {
            bidderEl.style.display = 'none';
        }

        // Action buttons
        var hasBid = !awaiting && p.state === 'auction' && p.current_bid && p.current_bid > 0;
        document.getElementById('acResetBidBtn').style.display  = hasBid ? '' : 'none';
        document.getElementById('acFinalizeBtn').style.display  = hasBid ? '' : 'none';
        var revealBtn = document.getElementById('acRevealBtn');
        if (revealBtn) {
            revealBtn.style.display = awaiting ? '' : 'none';
            revealBtn.disabled = !!state.revealBusy;
            if (!state.revealBusy) revealBtn.textContent = 'Reveal';
        }
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
            var disabledReason = team.can_bid_reason || (!player ? 'No player on stage' : 'Cannot bid');
            var classes = 'ac-team-btn' + (disabled ? ' ac-team-btn--disabled' : '') + (isActive ? ' ac-team-btn--active' : '');
            var onclick = disabled ? '' : 'onclick="acQuickBid(' + team.id + ')"';

            return '<div class="' + classes + '" ' + onclick + ' data-team-id="' + team.id + '">'
                + '<div class="ac-team-logo-wrap">'
                + (team.logo_url
                    ? '<img src="' + team.logo_url + '" alt="' + esc(team.name) + '" class="ac-team-logo" onerror="this.style.display=\'none\'">'
                    : '<div class="ac-team-logo-placeholder">' + sportIcon() + '</div>')
                + '</div>'
                + '<div class="ac-team-body">'
                + '  <div class="ac-team-top">'
                + '    <span class="ac-team-name">' + esc(team.name) + '</span>'
                + (isActive ? '<span class="ac-team-leading-badge">Leading</span>' : '')
                + '  </div>'
                + (team.manager ? '<span class="ac-team-manager">' + esc(team.manager) + '</span>' : '')
                + '  <div class="ac-team-purse">'
                + '    <div class="ac-team-purse__bar-wrap"><div class="ac-team-purse__bar' + barClass + '" style="width:' + pct.toFixed(1) + '%"></div></div>'
                + '    <div class="ac-team-purse__text"><span class="ac-team-purse__pts">' + fmtPts(team.remaining_points) + '</span><span class="ac-team-purse__sep">/</span>' + fmtPts(team.total_points) + '</div>'
                + '  </div>'
                + (disabled && !isActive
                    ? '<div class="ac-team-no-bid" title="' + esc(disabledReason) + '">' + esc(disabledReason) + '</div>'
                    : !isActive
                        ? '<div class="ac-team-next-bid" onclick="event.stopPropagation();acOpenBidModal(' + team.id + ')" title="Custom bid"><strong>' + fmtPts(team.next_bid) + '</strong> <span>pts</span></div>'
                        : (player && player.current_bid
                            ? '<div class="ac-team-leading-pts">' + fmtPts(player.current_bid) + ' pts</div>'
                            : ''))
                + '</div>'
                + '</div>';
        }).join('');

        grid.innerHTML = html;
        grid.scrollTop = scrollTop;
    }

    /* ── Quick Bid (one-tap: places next slab bid directly) ─────────────── */
    window.acQuickBid = function (teamId) {
        var team   = state.teams.find(function (t) { return t.id === teamId; });
        var player = state.currentPlayer;
        if (!team || !player || !team.can_bid) return;
        if (isAwaitingReveal(player) || player.state !== 'auction') return;

        var bidAmount = team.next_bid;

        // Visual feedback: briefly mark card as "placing"
        var card = document.querySelector('[data-team-id="' + teamId + '"]');
        if (card) card.classList.add('ac-team-btn--placing');

        jsonRpc(BID_URL, { player_id: player.id, team_id: team.id, bid_amount: bidAmount }, function (err, result) {
            if (card) card.classList.remove('ac-team-btn--placing');

            if (err || !result) { showToast('Network error. Please retry.', 'error'); return; }
            if (!result.success) { showToast(result.error || 'Bid failed', 'error'); return; }

            showToast('✅ ' + fmtPts(result.current_bid) + ' pts — ' + result.team_name, 'success');
            clearTimeout(state.pollTimer);
            poll();
        });
    };

    /* ── Modal ──────────────────────────────────────────────────────────── */
    window.acOpenBidModal = function (teamId) {
        var team   = state.teams.find(function (t) { return t.id === teamId; });
        var player = state.currentPlayer;

        if (!team || !player || player.state !== 'auction' || isAwaitingReveal(player)) return;
        state.selectedTeam = team;

        // Team header
        document.getElementById('acModalTeamLogo').src = team.logo_url || '';
        document.getElementById('acModalTeamName').textContent = team.name || '';
        document.getElementById('acModalTeamMeta').textContent =
            'Remaining: ' + fmtPts(team.remaining_points) + ' pts  |  Max call: ' + fmtPts(team.max_call) + ' pts';

        // Player info (masked for mystery)
        var hidden = isMysteryHidden(player);
        document.getElementById('acModalPlayerPhoto').src  = hidden
            ? DEFAULT_PHOTO
            : (player.photo_url || '');
        document.getElementById('acModalPlayerName').textContent  = hidden
            ? 'Mystery Player'
            : (player.name || '');
        document.getElementById('acModalPlayerRole').textContent  = hidden ? '' : playerMetaLine(player);
        var tBadge = document.getElementById('acModalTierBadge');
        tBadge.textContent   = hidden ? 'Mystery' : (player.tier_name || '');
        tBadge.style.color   = hidden ? '#c084fc' : (player.tier_color || '#e0b84a');
        tBadge.style.borderColor = hidden ? '#c084fc' : (player.tier_color || '#e0b84a');
        tBadge.style.background  = hexAlpha(hidden ? '#c084fc' : (player.tier_color || '#e0b84a'), 0.1);

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

    /* ── Slab helpers (mirrors owner_console.js logic) ─────────────────── */

    // Returns the increment for the slab that covers `amount`.
    // slabs must be sorted descending by from_amount.
    function slabStep(amount, slabs) {
        for (var i = 0; i < slabs.length; i++) {
            if (amount >= slabs[i].from_amount) return slabs[i].increment;
        }
        return 1; // fallback: increment by 1
    }

    // Snap `amount` DOWN to the nearest valid slab boundary.
    function snapToSlab(amount, slabs) {
        for (var i = 0; i < slabs.length; i++) {
            if (amount >= slabs[i].from_amount) {
                var base = slabs[i].from_amount;
                var inc  = slabs[i].increment;
                return base + Math.floor((amount - base) / inc) * inc;
            }
        }
        return amount;
    }

    /* Adjust bid by one slab increment in direction `dir` (+1 / -1) */
    window.acAdjustBid = function (dir) {
        var team = state.selectedTeam;
        if (!team) return;
        var input = document.getElementById('acBidInput');
        var cur   = parseInt(input.value, 10) || 0;
        var slabs = team.slabs && team.slabs.length ? team.slabs : state.slabs;
        var effectiveBase = team.effective_base || 1;

        if (dir > 0) {
            // If still at or below current live bid, jump to server's next_bid
            var liveBid = state.currentPlayer ? (state.currentPlayer.current_bid || 0) : 0;
            if (cur <= liveBid) {
                cur = team.next_bid;
            } else {
                cur = cur + slabStep(cur, slabs);
            }
        } else {
            // Step back one slab increment, snap to valid boundary
            var step = slabStep(cur, slabs);
            var decreased = cur - step;
            cur = Math.max(effectiveBase, snapToSlab(Math.max(0, decreased), slabs));
        }

        input.value = cur;
        validateBidInput(team, cur);
    };

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
            btn.textContent = 'Place Bid';

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
        if (!player || isAwaitingReveal(player)) return;
        var label = isMysteryHidden(player) ? 'Mystery Player' : (player.name || 'this player');
        if (!confirm('Reset the current bid for ' + label + '?')) return;

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
        var hidden = isMysteryHidden(player);

        // Populate confirm-sold modal (masked for mystery)
        document.getElementById('acSoldPlayerPhoto').src  = hidden
            ? DEFAULT_PHOTO
            : (player.photo_url || '');
        document.getElementById('acSoldPlayerName').textContent  = hidden
            ? 'Mystery Player'
            : (player.name || '');
        document.getElementById('acSoldPlayerRole').textContent  = hidden ? '' : playerMetaLine(player);
        var tierEl = document.getElementById('acSoldPlayerTier');
        tierEl.textContent   = hidden ? 'Mystery' : (player.tier_name || '');
        tierEl.style.color   = hidden ? '#c084fc' : (player.tier_color || '#e0b84a');
        tierEl.style.borderColor = hidden ? '#c084fc' : (player.tier_color || '#e0b84a');

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

        confirmBtn.disabled = true;
        confirmBtn.textContent = '⏳ Processing…';

        jsonRpc(FINALIZE_URL, { player_id: player.id }, function (err, result) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = 'Confirm Sold';

            if (err || !result) {
                showToast('Network error during finalization', 'error');
                return;
            }
            if (!result.success) {
                showToast(result.error || 'Finalization failed', 'error');
                return;
            }

            document.getElementById('acSoldConfirmModal').style.display = 'none';
            var bidModal = document.getElementById('acBidModal');
            if (bidModal) bidModal.style.display = 'none';
            state.selectedTeam = null;
            state.dicePicked = null;
            var diceStrip = document.getElementById('acDiceResult');
            if (diceStrip) diceStrip.style.display = 'none';

            if (result.awaiting_reveal || result.is_mystery) {
                showToast('Sold to ' + bidder + ' — tap Reveal to unlock identity', 'success');
            } else {
                state.currentPlayer = null;
                renderPlayer(null);
                renderTeams([], null);
                showToast(
                    '🎉 ' + (player.name || 'Player') + ' SOLD to ' + bidder
                    + ' — use Showcase to call the next player',
                    'success'
                );
            }
            renderShowcase();

            clearTimeout(state.pollTimer);
            poll();
        });
    };

    window.acRevealMystery = function () {
        var player = state.currentPlayer;
        if (!player || !isAwaitingReveal(player) || state.revealBusy) return;

        state.revealBusy = true;
        var btn = document.getElementById('acRevealBtn');
        if (btn) {
            btn.disabled = true;
            btn.textContent = 'Revealing…';
        }

        jsonRpc(REVEAL_URL, { player_id: player.id }, function (err, result) {
            state.revealBusy = false;
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Reveal';
            }
            if (err || !result) {
                showToast('Network error during reveal', 'error');
                return;
            }
            if (!result.success) {
                showToast(result.error || 'Reveal failed', 'error');
                return;
            }

            // Optimistically unlock console UI; poll refreshes full payload
            if (state.currentPlayer) {
                state.currentPlayer.mystery_revealed = true;
                state.currentPlayer.awaiting_reveal = false;
                state.currentPlayer.name = result.player_name || state.currentPlayer.name;
                if (result.photo_url) state.currentPlayer.photo_url = result.photo_url;
                if (result.sl_no != null) state.currentPlayer.sl_no = result.sl_no;
                renderPlayer(state.currentPlayer);
            }
            renderShowcase();
            showToast('🔓 Revealed: ' + (result.player_name || 'Player'), 'success');
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
