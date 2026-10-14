/* global fetch, localStorage */
'use strict';
(function () {

// ── State ──────────────────────────────────────────────────────────────
const S = {
    player: null,
    myTeam: null,
    teams: [],
    slabs: [],    // bid slabs sorted descending by from_amount (from server)
    presets: [],  // quick-select point values from tournament.preset_points
    tab: 'live',
    pendingBid: null,
    pollTimer: null,
    revoke: null, // { feature_on, remaining, max, used, can_revoke }
    bidTimer: null,
    _bidTimerTick: null,
    _bidTimerFroze: false,
    // Track last known bid to detect rival changes between polls
    _lastBid: { playerId: null, bid: 0, teamId: null },
    _counterTs: null,   // last-seen counter_started_at; null = not yet initialised
    _counterInit: false,
    _sseStarted: false,
    _timerEpoch: 0,
    _bidTimerPoll: null,
};

// ── Tiny helpers ───────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const esc = s => (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const fmt = n => (n||0).toLocaleString();
const fmtU = n => (window.fmtUnit ? window.fmtUnit(n) : (fmt(n) + ' pts'));
function unitName() {
    return (window.AuctionPointUnit && window.AuctionPointUnit.name && window.AuctionPointUnit.name()) || 'Points';
}
function maxCallPct(mine, teams) {
    var mineN = Number(mine) || 0;
    if (mineN <= 0) return 0;
    var vals = (teams || []).map(function (t) { return Number(t.max_call) || 0; }).filter(function (v) { return v > 0; });
    var hi = vals.length ? Math.max.apply(null, vals) : 0;
    if (hi <= 0) return 100;
    return Math.round((mineN / hi) * 100);
}

function maxCallBand(pct) {
    if (pct >= 80) return 'high';
    if (pct >= 50) return 'med';
    return 'low';
}

function paintBaseMaxCall(myTeam, teams) {
    var wrap = $('ocBaseMaxCall');
    var valEl = $('ocBaseMaxCallVal');
    if (!wrap || !valEl) return;
    var mine = Number(myTeam && myTeam.max_call) || 0;
    var pct = maxCallPct(mine, teams);
    var band = maxCallBand(pct);
    valEl.textContent = mine > 0 ? fmtU(mine) : '—';
    wrap.classList.remove('oc-maxcall-high', 'oc-maxcall-med', 'oc-maxcall-low');
    wrap.classList.add('oc-maxcall-' + band);
    wrap.title = mine > 0
        ? ('Max call is ' + pct + '% of the highest among teams (80–100% green, 50–79% yellow, below 50% red)')
        : 'No max call for this player';
}

function applyPointUnit(unit) {
    if (unit && window.AuctionPointUnit && window.AuctionPointUnit.setConfig) {
        window.AuctionPointUnit.setConfig(unit);
    }
    var el = $('ocConfirmPtsUnit');
    if (el) el.textContent = String(unitName()).toUpperCase();
}
function show(id, v) { const e=$(id); if(e) e.style.display = v?'':'none'; }
function up(v) { return v ? String(v).toUpperCase() : ''; }
function txt(id, v)  { const e=$(id); if(e) e.textContent = v||'—'; }
function src(id, v)  { const e=$(id); if(e) e.src = v||''; }

function toast(msg, type) {
    const el = $('ocToast');
    if (!el) return;
    el.textContent = msg;
    el.className = 'oc-toast oc-show' + (type?' oc-'+type:'');
    clearTimeout(el._t);
    el._t = setTimeout(() => el.className='oc-toast', 3000);
}

// ── User menu (logout dropdown) ────────────────────────────────
window.ocToggleUserMenu = function(e) {
    e.stopPropagation();
    const menu = $('ocUserMenu');
    if (menu) menu.classList.toggle('oc-menu-open');
};
// Close on outside click
document.addEventListener('click', () => {
    const menu = $('ocUserMenu');
    if (menu) menu.classList.remove('oc-menu-open');
});

// ── Projector-style SOLD / UNSOLD seal on the player photo ──
function setSealArcText(textId, value) {
    var el = $(textId);
    if (!el) return;
    var path = el.querySelector('textPath');
    if (path) path.textContent = value || '';
}

function showPhotoStatus(kind, soldData) {
    var overlay = $('ocPhotoStatus');
    if (!overlay) return;
    var isSold = kind === 'sold';
    overlay.setAttribute('data-kind', isSold ? 'sold' : 'unsold');
    setSealArcText('ocSealArcTopText', isSold ? 'SOLD TO' : 'NO BID');
    var teamName = ((soldData && (soldData.name || soldData.team || soldData.team_name)) || (isSold ? 'TEAM' : 'UNSOLD')).toUpperCase();
    setSealArcText('ocSealArcBotText', teamName);

    var logoEl = $('ocStatusSealLogo');
    var logoUrl = (soldData && (soldData.logo_url || soldData.team_logo_url)) || '';
    if (logoEl) {
        if (isSold && logoUrl) {
            logoEl.src = logoUrl;
            logoEl.classList.add('is-on');
        } else {
            logoEl.removeAttribute('src');
            logoEl.classList.remove('is-on');
        }
    }
    overlay.classList.remove('oc-status-show');
    void overlay.offsetWidth;
    overlay.classList.add('oc-status-show');
}

function showSoldOverlay(soldData) {
    showPhotoStatus('sold', soldData || {});
}
function hideSoldOverlay() {
    var overlay = $('ocPhotoStatus');
    if (overlay) overlay.classList.remove('oc-status-show');
}
function showUnsoldOverlay() {
    showPhotoStatus('unsold', null);
}
function hideUnsoldOverlay() {
    var overlay = $('ocPhotoStatus');
    if (overlay && overlay.getAttribute('data-kind') === 'unsold') {
        overlay.classList.remove('oc-status-show');
    }
}

// ── Tab switching ──────────────────────────────────────────────────────
window.ocSwitchTab = function(tab, btn) {
    ['live','teams','mysquad'].forEach(t => {
        const map = {live:'Live', teams:'Teams', mysquad:'MySquad'};
        const el = $('ocTab'+map[t]);
        if (el) {
            // Only toggle the class — never set inline display.
            // On mobile CSS hides non-active panes; on desktop the media
            // query forces all panes visible via !important, so inline
            // display:none would fight against it.
            if (t === tab) el.classList.add('oc-tab-active');
            else           el.classList.remove('oc-tab-active');
        }
    });
    document.querySelectorAll('.oc-tab-btn').forEach(b => b.classList.remove('oc-tab-btn-active'));
    if (btn) btn.classList.add('oc-tab-btn-active');
    S.tab = tab;
    if (tab === 'teams')   renderTeamsFull();
    if (tab === 'mysquad') renderMySquad();
};

// ── Rival bid flash ────────────────────────────────────────────────────
function flashRivalBid(player) {
    const teamName = (player.current_bid_team && player.current_bid_team.name) || 'A team';
    const amount   = fmtU(player.current_bid);

    // 1. Slide-in alert banner inside the showcase card
    const alertEl = $('ocRivalAlert');
    const msgEl   = $('ocRivalMsg');
    if (alertEl && msgEl) {
        msgEl.textContent = teamName + ' raised to ' + amount + '!';
        // Reset animation by toggling class
        alertEl.classList.remove('oc-rival-show');
        void alertEl.offsetWidth; // reflow
        alertEl.classList.add('oc-rival-show');
        clearTimeout(alertEl._hideT);
        alertEl._hideT = setTimeout(() => alertEl.classList.remove('oc-rival-show'), 5000);
    }

    // 2. Border-flash the showcase card (3 pulses)
    const card = $('ocShowcaseCard');
    if (card) {
        card.classList.remove('oc-rival-bid');
        void card.offsetWidth; // reflow to restart keyframes
        card.classList.add('oc-rival-bid');
        card.addEventListener('animationend', () => card.classList.remove('oc-rival-bid'), {once:true});
    }

    // 3. Toast notification
    toast('🔥 ' + teamName + ' — ' + amount + '!', 'warn');

    // 4. Haptic feedback on mobile (two short buzzes)
    if (navigator.vibrate) navigator.vibrate([80, 60, 80]);
}

function paintSoldCard(p) {
    var card = $('ocSoldCard');
    if (!card) return;
    var sold = !!(p && p.state === 'sold');
    var unsold = !!(p && p.state === 'unsold');
    if (!sold && !unsold) {
        card.style.display = 'none';
        return;
    }
    card.style.display = 'block';
    card.className = 'oc-sold-card ' + (sold ? 'is-sold' : 'is-unsold');
    txt('ocSoldLabel', sold ? 'SOLD TO' : 'UNSOLD');
    var team = sold ? (p.sold_team || p.current_bid_team || {}) : {};
    txt('ocSoldTeam', sold ? (team.name || '—') : '');
    var logo = $('ocSoldLogo');
    if (logo) {
        if (sold && team.logo_url) {
            logo.src = team.logo_url;
            logo.style.display = '';
        } else {
            logo.style.display = 'none';
        }
    }
    var amount = sold ? (Number(p.sold_points) || Number(p.current_bid) || 0) : 0;
    txt('ocSoldAmount', amount ? fmtU(amount) : '');
}

function syncStageChrome() {
    var closed = !!(S.player && (S.player.state === 'sold' || S.player.state === 'unsold'));
    var box = $('ocCurrentBidBox');
    var raise = $('ocRaiseBtn');
    var timer = $('ocBidTimer');
    var lead = $('ocLeadingTeam');
    if (box) box.style.display = closed ? 'none' : '';
    if (raise) raise.style.display = closed ? 'none' : '';
    if (closed && timer) timer.style.display = 'none';
    if (closed && lead) lead.style.display = 'none';
    paintSoldCard(S.player);
}

// ── Player entrance shutter (same idea as the projector curtains) ──
var _ocShownPid = null;
var _ocPhotoReq = 0;
var _ocCurtain = { shut: false, ready: null, t1: null, t2: null, t3: null };

function ocReducedMotion() {
    return window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

function clearCurtainTimers() {
    ['t1', 't2', 't3'].forEach(function (k) {
        if (_ocCurtain[k]) { clearTimeout(_ocCurtain[k]); _ocCurtain[k] = null; }
    });
}

function beginStageCurtain(instant) {
    var el = $('ocStageCurtain');
    if (!el || ocReducedMotion()) {
        _ocCurtain.shut = true;
        return;
    }
    clearCurtainTimers();
    _ocCurtain.ready = null;
    el.classList.remove('is-open');
    el.classList.add('is-run');
    if (instant) {
        el.classList.add('is-instant', 'is-shut');
        _ocCurtain.shut = true;
        return;
    }
    _ocCurtain.shut = false;
    el.classList.remove('is-instant');
    void el.offsetWidth;
    el.classList.add('is-shut');
    _ocCurtain.t1 = setTimeout(function () {
        _ocCurtain.shut = true;
        if (_ocCurtain.ready) {
            var fn = _ocCurtain.ready;
            _ocCurtain.ready = null;
            fn();
        }
    }, 450);
}

function finishStageCurtain(onShut) {
    var el = $('ocStageCurtain');
    function swapThenOpen() {
        if (onShut) onShut();
        if (!el || ocReducedMotion()) return;
        el.classList.remove('is-instant');
        _ocCurtain.t2 = setTimeout(function () {
            el.classList.remove('is-shut');
            el.classList.add('is-open');
            _ocCurtain.t3 = setTimeout(function () {
                el.classList.remove('is-run', 'is-open', 'is-instant');
                _ocCurtain.shut = false;
            }, 560);
        }, 140);
    }
    if (!el || ocReducedMotion()) {
        if (onShut) onShut();
        return;
    }
    if (_ocCurtain.shut) swapThenOpen();
    else _ocCurtain.ready = swapThenOpen;
}

function applyPlayerPhoto(p) {
    var img = $('ocPlayerPhoto');
    if (!img) return;
    var next = (p && p.photo_url) || '';
    if ((img.getAttribute('src') || '') === next) return;
    if (next) img.src = next;
    else img.removeAttribute('src');
}

// ── Render: player showcase ────────────────────────────────────────────
function renderPlayer(p) {
    if (!p) {
        show('ocWaiting', true); show('ocPlayerWrap', false);
        hideSoldOverlay();
        paintSoldCard(null);
        return;
    }
    var nextId = p.id;
    var changed = !!(_ocShownPid && nextId && String(nextId) !== String(_ocShownPid));
    var wrap = $('ocPlayerWrap');
    var wasHidden = !wrap || wrap.style.display === 'none';

    function reveal() {
        show('ocWaiting', false);
        show('ocPlayerWrap', true);
        paintPlayerFace(p);
    }

    if (!changed) {
        _ocShownPid = nextId || _ocShownPid;
        reveal();
        return;
    }
    _ocShownPid = nextId;
    if (wasHidden) beginStageCurtain(true);
    else beginStageCurtain(false);
    show('ocWaiting', false);
    show('ocPlayerWrap', true);

    var req = ++_ocPhotoReq;
    var started = false;
    function go() {
        if (req !== _ocPhotoReq || started) return;
        started = true;
        finishStageCurtain(reveal);
    }
    var nextSrc = p.photo_url || '';
    if (!nextSrc) { go(); return; }
    var pre = new Image();
    pre.onload = go;
    pre.onerror = go;
    pre.src = nextSrc;
    if (pre.complete) go();
}

function paintPlayerFace(p) {
    // Show SOLD/UNSOLD overlay based on player state; hide for all other states
    if (p.state === 'sold') {
        var buyer = p.sold_team || p.current_bid_team || {};
        showSoldOverlay({
            name: buyer.name,
            logo_url: buyer.logo_url,
            sold_points: p.sold_points || p.current_bid || 0,
        });
        closeOwnerBids();
    } else if (p.state === 'unsold') {
        showUnsoldOverlay();
        closeOwnerBids();
    } else {
        hideSoldOverlay();
        hideUnsoldOverlay();
    }

    applyPlayerPhoto(p);
    txt('ocPlayerName', up(p.name));
    txt('ocPlayerRole', up(p.role) || '—');

    const styleEl = $('ocPlayerStyle');
    if (styleEl) {
        const parts = [p.batting_style, p.bowling_style].filter(Boolean).map(up);
        styleEl.textContent = parts.join(' · ');
        styleEl.style.display = parts.length ? '' : 'none';
    }

    const pill = $('ocTierPill');
    if (pill) { pill.textContent = up(p.tier_name) || '—'; pill.style.background = p.tier_color || ''; }

    const ring = $('ocPhotoRing');
    if (ring) ring.style.background = p.tier_color ? `conic-gradient(${p.tier_color},#fff3,${p.tier_color})` : '';

    txt('ocSlNo', p.sl_no ? '#' + p.sl_no : '');
    txt('ocBasePrice', p.base_price ? fmtU(p.base_price) : '—');
    paintBaseMaxCall(S.myTeam, S.teams);
    txt('ocCurrentBid', p.current_bid ? fmtU(p.current_bid) : 'No bids yet');

    const hasLeader = stageOpen(p) && p.current_bid_team && p.current_bid_team.name;
    show('ocLeadingTeam', !!hasLeader);
    if (hasLeader) {
        src('ocLeadingLogo', p.current_bid_team.logo_url);
        txt('ocLeadingName', p.current_bid_team.name);
    }
    syncStageChrome();
}

// ── Render: bid panel ──────────────────────────────────────────────────
function stageOpen(player) {
    return !!(player && player.state === 'auction');
}

function closeOwnerBids() {
    if (S.myTeam) {
        S.myTeam.can_bid = false;
        S.myTeam.is_leading = false;
        S.myTeam.can_bid_reason = 'Waiting for the next player';
    }
    if (S.bidTimer) {
        S.bidTimer.running = false;
        S.bidTimer.frozen = false;
        S.bidTimer.held = false;
    }
    renderBidPanel(S.myTeam, S.player);
    renderRevoke();
    paintBidTimer();
}

function paintHeaderIdentity(myTeam, owner) {
    var name = (myTeam && myTeam.name) || '';
    var logo = (myTeam && myTeam.logo_url) || '';
    var ownerName = (myTeam && myTeam.manager) || (owner && owner.name) || '';
    txt('ocHdrTeamName', name || 'No team linked');
    var ownerEl = $('ocHdrOwnerName');
    if (ownerEl) {
        ownerEl.textContent = ownerName ? ('Owner · ' + ownerName) : '';
    }
    var img = $('ocHdrTeamLogo');
    var fb = $('ocHdrTeamLogoFb');
    if (logo && img) {
        img.src = logo;
        img.style.display = '';
        img.removeAttribute('hidden');
        if (fb) {
            fb.setAttribute('hidden', 'hidden');
            fb.textContent = '';
        }
    } else {
        if (img) {
            img.style.display = 'none';
            img.removeAttribute('src');
        }
        if (fb) {
            fb.removeAttribute('hidden');
            fb.textContent = (name || '?').charAt(0).toUpperCase();
        }
    }
}

function paintHeaderPurse(myTeam) {
    const purse = $('ocHeaderPurse');
    const squad = $('ocHeaderSquad');
    if (purse) {
        purse.textContent = myTeam
            ? (fmt(myTeam.remaining_points) + ' left')
            : '—';
    }
    if (squad) {
        if (!myTeam) squad.textContent = '—';
        else {
            var max = myTeam.max_players ? myTeam.max_players : '—';
            squad.textContent = (myTeam.player_count || 0) + ' / ' + max;
        }
    }
}

function renderBidPanel(myTeam, player) {
    paintHeaderPurse(myTeam);
    if (!myTeam || !player) {
        renderQuickBidBox(false, 'No player on stage');
        show('ocLeadWarn', false);
        ocCloseCustomBid();
        syncStageChrome();
        return;
    }

    if (!stageOpen(player)) {
        show('ocLeadWarn', false);
        ocCloseCustomBid();
        const closedInput = $('ocBidInput');
        const closedBtn = $('ocBidCta');
        const closedReason = $('ocBidReason');
        if (closedInput) { closedInput.disabled = true; closedInput.value = ''; }
        if (closedBtn) closedBtn.disabled = true;
        if (closedReason) {
            closedReason.textContent = 'Waiting for the next player';
            closedReason.className = 'oc-bid-reason oc-reason-err';
        }
        renderPresets([], myTeam);
        renderQuickBidBox(false, 'Waiting for the next player', false);
        const revokeBtn = $('ocRevokeBtn');
        if (revokeBtn) revokeBtn.disabled = true;
        syncStageChrome();
        return;
    }

    src('ocMyTeamLogo', myTeam.logo_url);
    txt('ocMyTeamName', myTeam.name);

    const pct = myTeam.total_points > 0 ? (myTeam.remaining_points / myTeam.total_points * 100) : 0;
    const barFill = $('ocMyPurseBar');
    if (barFill) barFill.style.width = pct + '%';
    txt('ocMyPurse', fmt(myTeam.remaining_points)+' / '+fmtU(myTeam.total_points));
    txt('ocCustomSquad', (myTeam.player_count || 0) + ' / ' + (myTeam.max_players || '—'));
    txt('ocMaxCallVal', myTeam.max_call > 0 ? fmtU(myTeam.max_call) : '—');
    paintBaseMaxCall(myTeam, S.teams);
    show('ocLeadWarn', !!myTeam.is_leading);
    if (myTeam.is_leading) ocCloseCustomBid();

    const input   = $('ocBidInput');
    const bidBtn  = $('ocBidCta');
    const reasonEl = $('ocBidReason');

    if (ownerTimerHeld() || (ownerBidFrozen() && !myTeam.is_leading)) {
        var lockReason = ownerTimerHeld()
            ? 'Timer on hold'
            : 'Time up — only the last bid stays open';
        if (input) { input.disabled = true; input.value = ''; }
        if (bidBtn) bidBtn.disabled = true;
        if (reasonEl) {
            reasonEl.textContent = lockReason;
            reasonEl.className = 'oc-bid-reason oc-reason-err';
        }
        renderPresets(slabPresetBids(myTeam), myTeam);
        renderQuickBidBox(false, lockReason, false);
    } else if (!myTeam.can_bid) {
        if (input) { input.disabled = true; input.value = ''; }
        if (bidBtn) bidBtn.disabled = true;
        if (reasonEl) { reasonEl.textContent = '🚫 '+( myTeam.can_bid_reason || 'Cannot bid'); reasonEl.className='oc-bid-reason oc-reason-err'; }
        renderPresets(slabPresetBids(myTeam), myTeam);
        renderQuickBidBox(false, myTeam.can_bid_reason || 'Cannot bid', myTeam.is_leading);
    } else {
        if (input) {
            const nextBidVal   = myTeam.next_bid || myTeam.effective_base || 1;
            const isNewPlayer  = !input.dataset.pid || input.dataset.pid !== String(player.id);
            const curInputVal  = parseInt(input.value, 10) || 0;

            if (isNewPlayer) {
                // Fresh player on stage — always reset to the server's next_bid
                input.value = nextBidVal;
                input.dataset.pid = String(player.id);
            } else if (curInputVal < nextBidVal) {
                // A rival raised the bid and the current input is now below the new minimum;
                // bump it up so the owner can't accidentally submit a stale low value.
                input.value = nextBidVal;
            }
            // If the owner manually typed a value above next_bid, leave it untouched.
            input.disabled = false;
            input.min = myTeam.effective_base || 1;
        }
        if (bidBtn) bidBtn.disabled = false;
        if (reasonEl) {
            reasonEl.textContent = myTeam.max_call > 0 ? 'Max call for this player: '+fmtU(myTeam.max_call) : '';
            reasonEl.className = 'oc-bid-reason oc-reason-ok';
        }
        renderPresets(slabPresetBids(myTeam), myTeam);
        renderQuickBidBox(true, myTeam.next_bid || myTeam.effective_base || 1);
    }
    syncStageChrome();
}

function isPurseOrSquadBlock(reason) {
    return /squad full|tier slot|budget|purse|max call|no budget/i.test(String(reason || ''));
}

function paintRaiseButton(mode, detail) {
    const raise = $('ocRaiseBtn');
    const main = $('ocRaiseMain');
    const sub = $('ocRaiseSub');
    if (!raise || !main) return;
    raise.classList.remove('is-quiet', 'is-locked', 'is-blocked');
    if (sub) {
        sub.textContent = '';
        sub.hidden = true;
    }
    if (mode === 'bid') {
        raise.disabled = false;
        main.textContent = 'Bid ' + fmtU(detail);
        return;
    }
    raise.disabled = true;
    if (mode === 'lead') {
        raise.classList.add('is-quiet');
        main.textContent = 'Your bid stands';
        return;
    }
    if (mode === 'limit') {
        raise.classList.add('is-locked', 'is-blocked');
        var max = Number(S.myTeam && S.myTeam.max_call) || 0;
        main.innerHTML = 'Max call <span class="oc-raise-max">' + esc(max > 0 ? fmtU(max) : '—') + '</span>';
        if (sub) {
            sub.hidden = false;
            sub.textContent = "You're not able to bid this player because of " + (detail || 'a limit');
        }
        return;
    }
    raise.classList.add('is-locked');
    main.textContent = detail || 'Cannot bid';
}

// ── Quick-bid box: update Current Bid box clickability ────────────────
// canBid=true  → nextBid is the pts value to place
// canBid=false, isLeading=true → owner already leads; show crown, no text
// canBid=false, isLeading=false → nextBid is the reason string
function renderQuickBidBox(canBid, nextBidOrReason, isLeading) {
    const box  = $('ocCurrentBidBox');
    const hint = $('ocQbHint');
    if (box) {
        if (canBid) {
            box.classList.add('oc-qb-active');
            box.classList.remove('oc-qb-disabled', 'oc-qb-leading');
            if (hint) {
                hint.textContent = ocIsTouchUi()
                    ? 'Double-tap or hold the button for a custom bid'
                    : 'Double-click the button for a custom bid';
            }
        } else if (isLeading) {
            box.classList.add('oc-qb-leading');
            box.classList.remove('oc-qb-active', 'oc-qb-disabled');
            if (hint) hint.textContent = '';
        } else {
            box.classList.add('oc-qb-disabled');
            box.classList.remove('oc-qb-active', 'oc-qb-leading');
            if (hint) hint.textContent = '';
        }
    }
    if (canBid) {
        paintRaiseButton('bid', nextBidOrReason);
    } else if (isLeading) {
        paintRaiseButton('lead');
    } else if (isPurseOrSquadBlock(nextBidOrReason)) {
        paintRaiseButton('limit', nextBidOrReason);
    } else {
        paintRaiseButton('locked', nextBidOrReason);
    }
}

// ── Quick Bid: one-tap bid at next slab value ─────────────────────────
function ownerTimerHeld() {
    const t = S.bidTimer;
    return !!(t && t.enabled && t.held);
}

function ownerBidFrozen() {
    const t = S.bidTimer;
    if (!t || !t.enabled) return false;
    if (t.held) return true;
    if (t.frozen) return true;
    if (!t.running) return false;
    return (t.remainUntil - Date.now()) <= 0;
}

function ownerBidLockToast() {
    return ownerTimerHeld()
        ? 'Timer is on hold. You can bid when it resumes.'
        : 'Time is up. Only the last bid stays open.';
}

var OC_CLOCK_CIRC = 2 * Math.PI * 15.5;
var _ocAudio = null;
var _clockBeepKey = '';

function ocAudioCtx() {
    var AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) return null;
    if (!_ocAudio) _ocAudio = new AC();
    if (_ocAudio.state === 'suspended') {
        try { _ocAudio.resume(); } catch (e) {}
    }
    return _ocAudio;
}

function unlockClockSound() {
    ocAudioCtx();
}

['click', 'touchstart', 'keydown'].forEach(function (ev) {
    document.addEventListener(ev, unlockClockSound, { once: true, capture: true });
});

function playCriticalTick(shown) {
    var c = ocAudioCtx();
    if (!c || c.state !== 'running') return;
    try {
        var t = c.currentTime;
        var urgent = shown <= 1;
        var freq = urgent ? 1240 : (shown <= 2 ? 980 : 820);
        var osc = c.createOscillator();
        var g = c.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, t);
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(urgent ? 0.16 : 0.1, t + 0.012);
        g.gain.exponentialRampToValueAtTime(0.0001, t + (urgent ? 0.16 : 0.09));
        osc.connect(g);
        g.connect(c.destination);
        osc.start(t);
        osc.stop(t + 0.2);
    } catch (e) {}
}

function clockBeep(blink, shown, playerId) {
    if (!blink) {
        _clockBeepKey = '';
        return;
    }
    var key = String(playerId || 0) + ':' + shown;
    if (key === _clockBeepKey) return;
    var c = ocAudioCtx();
    if (!c || c.state !== 'running') return;
    _clockBeepKey = key;
    playCriticalTick(shown);
}

function paintClock(left, total, blink) {
    const clock = $('ocClock');
    const num = $('ocClockNum');
    const arc = $('ocClockArc');
    if (!clock) return;
    clock.hidden = false;
    clock.classList.toggle('is-blink', !!blink);
    var shown = Math.ceil(left);
    if (num && num.textContent !== String(shown)) num.textContent = shown;
    var span = total > 0 ? total : left;
    var gone = span > 0 ? Math.min(1, Math.max(0, 1 - (left / span))) : 1;
    if (arc) {
        arc.style.strokeDasharray = String(OC_CLOCK_CIRC);
        arc.style.strokeDashoffset = String(OC_CLOCK_CIRC * gone);
    }
}

function hideClock() {
    const clock = $('ocClock');
    if (!clock) return;
    clock.hidden = true;
    clock.classList.remove('is-blink');
}

function paintBidTimer() {
    const el = $('ocBidTimer');
    const msg = $('ocClockMsg');
    if (!el) return;
    function say(text) { if (msg) msg.textContent = text || ''; }
    if (S.player && !stageOpen(S.player)) {
        el.style.display = 'none';
        hideClock();
        clockBeep(false);
        syncStageChrome();
        return;
    }
    const t = S.bidTimer;
    if (!t || !t.enabled) {
        el.style.display = 'none';
        hideClock();
        clockBeep(false);
        say('');
        return;
    }
    el.style.display = '';
    const leading = !!(S.myTeam && S.myTeam.is_leading);
    if (t.held) {
        var heldLeft = Math.max(0, t.remaining || 0);
        el.className = 'oc-bid-timer is-paused';
        paintClock(heldLeft, t.seconds || heldLeft, false);
        clockBeep(false);
        say('Timer on hold');
        if (S.myTeam && !S._bidTimerHeld) {
            S._bidTimerHeld = true;
            S.myTeam.can_bid = false;
            S.myTeam.can_bid_reason = 'Timer on hold';
            renderBidPanel(S.myTeam, S.player);
            renderRevoke();
        }
        return;
    }
    S._bidTimerHeld = false;
    if (!t.running && !t.frozen) {
        el.className = 'oc-bid-timer is-idle';
        hideClock();
        clockBeep(false);
        say('Waiting for the player');
        return;
    }
    const left = t.frozen ? 0 : Math.max(0, (t.remainUntil - Date.now()) / 1000);
    if (left <= 0) {
        t.frozen = true;
        t.running = false;
        hideClock();
        clockBeep(false);
        if (leading) {
            el.className = 'oc-bid-timer is-held';
            say('Your bid stands. Other owners are closed.');
        } else {
            el.className = 'oc-bid-timer is-frozen';
            say('Time up. You can no longer bid.');
        }
        if (!S._bidTimerFroze && S.myTeam && S.player && !leading) {
            S._bidTimerFroze = true;
            S.myTeam.can_bid = false;
            S.myTeam.can_bid_reason = 'Time up — only the last bid stays open';
            renderBidPanel(S.myTeam, S.player);
            renderRevoke();
        }
        return;
    }
    S._bidTimerFroze = false;
    var total = t.seconds || left;
    var warnAt = Math.max(1, Math.round(total * 0.25));
    var shown = Math.ceil(left);
    var blink = shown <= warnAt;
    paintClock(left, total, blink);
    clockBeep(blink, shown, S.player && S.player.id);
    if (leading) {
        el.className = 'oc-bid-timer is-held';
        say('Others can still raise');
        return;
    }
    el.className = 'oc-bid-timer is-running';
    say('');
}

function syncBidTimer(timer) {
    timer = timer || {};
    var epoch = Number(timer.epoch || 0);
    if (epoch && S._timerEpoch && epoch + 0.0001 < S._timerEpoch) return;
    if (S.bidTimer && S.bidTimer.held && timer.running && !timer.held) {
        if ((Number(timer.remaining) || 0) + 0.6 < (Number(S.bidTimer.remaining) || 0)) return;
    }
    if (epoch) S._timerEpoch = epoch;
    if (!timer.enabled) {
        S.bidTimer = {enabled: false, frozen: false, running: false, held: false, seconds: 0};
        S._bidTimerFroze = false;
        S._bidTimerHeld = false;
    } else if (timer.held) {
        S.bidTimer = {
            enabled: true,
            frozen: false,
            running: false,
            held: true,
            seconds: timer.seconds || 0,
            remaining: Math.max(0, timer.remaining || 0),
            epoch: epoch,
        };
        S._bidTimerFroze = false;
    } else if (timer.frozen) {
        S.bidTimer = {enabled: true, frozen: true, running: false, held: false, seconds: timer.seconds || 0};
        S._bidTimerHeld = false;
    } else if (timer.running) {
        S.bidTimer = {
            enabled: true,
            frozen: false,
            running: true,
            held: false,
            seconds: timer.seconds || 0,
            remaining: Math.max(0, timer.remaining || 0),
            remainUntil: Date.now() + Math.max(0, (timer.remaining || 0) * 1000),
            epoch: epoch,
        };
        S._bidTimerFroze = false;
        S._bidTimerHeld = false;
    } else {
        S.bidTimer = {enabled: true, frozen: false, running: false, held: false, seconds: timer.seconds || 0};
        S._bidTimerFroze = false;
        S._bidTimerHeld = false;
    }
    paintBidTimer();
    if (!S._bidTimerTick) {
        S._bidTimerTick = setInterval(paintBidTimer, 250);
    }
}

window.ocQuickBid = function() {
    const { myTeam, player } = S;
    if (!stageOpen(player)) return;
    if (ownerTimerHeld() || (ownerBidFrozen() && !(myTeam && myTeam.is_leading))) {
        toast(ownerBidLockToast(), 'err');
        paintBidTimer();
        return;
    }
    if (!myTeam || !player || !myTeam.can_bid) return;

    const bidAmount = myTeam.next_bid || myTeam.effective_base || 1;
    const box = $('ocCurrentBidBox');
    const raise = $('ocRaiseBtn');
    let placed = false;
    if (box) box.classList.add('oc-qb-placing');
    if (raise) raise.disabled = true;

    fetch('/auction/owner/place-bid', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ jsonrpc:'2.0', method:'call', params:{
            player_id: player.id, team_id: myTeam.id, bid_amount: bidAmount
        }}),
    })
    .then(r => r.json())
    .then(resp => {
        const res = resp.result || resp;
        if (res.success) {
            placed = true;
            toast('⚡ Quick Bid: ' + fmtU(bidAmount) + '!', 'ok');
            fetchData();
        } else {
            toast(res.error || 'Bid failed', 'err');
        }
    })
    .catch(() => toast('Network error. Please retry.', 'err'))
    .finally(() => {
        if (box) box.classList.remove('oc-qb-placing');
        if (!placed && S.myTeam && S.player) renderBidPanel(S.myTeam, S.player);
    });
};

// ── Render revoke button ────────────────────────────────────────────────
function renderRevoke() {
    const rv   = S.revoke;
    const wrap = $('ocRevokeWrap');
    const btn  = $('ocRevokeBtn');
    const hint = $('ocRevokeHint');
    if (!wrap) return;

    if (!rv || !rv.feature_on) {
        wrap.style.display = 'none';
        return;
    }

    wrap.style.display = 'flex';
    const canRevoke = rv.can_revoke && rv.remaining > 0 && !ownerBidFrozen();
    if (btn) btn.disabled = !canRevoke;
    if (hint) {
        if (rv.remaining <= 0) {
            hint.textContent = 'No revokes left';
        } else {
            hint.textContent = rv.remaining + '/' + rv.max + ' left';
        }
    }
}

function slabPresetBids(myTeam) {
    var start = Number((myTeam && (myTeam.next_bid || myTeam.effective_base)) || 0);
    var max = Number((myTeam && myTeam.max_call) || 0);
    var slabs = S.slabs || [];
    var out = [];
    var v = start;
    var i;
    for (i = 0; i < 6; i++) {
        if (max && v > max) break;
        if (v > 0 && out.indexOf(v) === -1) out.push(v);
        v = v + (slabStep(v, slabs) || 1);
    }
    (S.presets || []).forEach(function (pt) {
        pt = Number(pt);
        if (pt >= start && (!max || pt <= max) && out.indexOf(pt) === -1) out.push(pt);
    });
    out.sort(function (a, b) { return a - b; });
    return out;
}

window.ocOpenCustomBid = function () {
    if (!stageOpen(S.player) || !S.myTeam || S.myTeam.is_leading) return;
    renderBidPanel(S.myTeam, S.player);
    var ov = $('ocCustomBidOverlay');
    if (ov) ov.style.display = 'flex';
};
window.ocCloseCustomBid = function () {
    var ov = $('ocCustomBidOverlay');
    if (ov) ov.style.display = 'none';
};

function ocIsTouchUi() {
    return window.matchMedia && (
        window.matchMedia('(pointer: coarse)').matches ||
        window.matchMedia('(hover: none)').matches
    );
}

function bindBidGestures(el) {
    if (!el || el._ocBound) return;
    el._ocBound = true;
    var holdTimer = null;
    var holdFired = false;
    var tapTimer = null;
    var startX = 0;
    var startY = 0;
    var downAt = 0;

    function clearHold() {
        if (holdTimer) { clearTimeout(holdTimer); holdTimer = null; }
    }
    function isTouchPtr(ev) {
        return ev.pointerType === 'touch' || (ev.pointerType !== 'mouse' && ocIsTouchUi());
    }
    function canGesture() {
        return stageOpen(S.player) && S.myTeam && S.myTeam.can_bid && !S.myTeam.is_leading;
    }
    function openCustom() {
        if (!canGesture()) return;
        ocOpenCustomBid();
    }

    el.addEventListener('pointerdown', function (ev) {
        if (ev.button && ev.button !== 0) return;
        if (el.disabled) return;
        holdFired = false;
        downAt = Date.now();
        startX = ev.clientX;
        startY = ev.clientY;
        if (!isTouchPtr(ev) || !canGesture()) return;
        clearHold();
        holdTimer = setTimeout(function () {
            holdTimer = null;
            holdFired = true;
            if (navigator.vibrate) {
                try { navigator.vibrate(12); } catch (e) {}
            }
            openCustom();
        }, 450);
    });
    el.addEventListener('pointermove', function (ev) {
        if (!holdTimer) return;
        if (Math.abs(ev.clientX - startX) > 14 || Math.abs(ev.clientY - startY) > 14) clearHold();
    });
    el.addEventListener('pointerup', clearHold);
    el.addEventListener('pointercancel', function () {
        var elapsed = Date.now() - downAt;
        clearHold();
        if (!holdFired && elapsed >= 400 && canGesture()) {
            holdFired = true;
            if (navigator.vibrate) {
                try { navigator.vibrate(12); } catch (e) {}
            }
            openCustom();
        }
    });
    el.addEventListener('contextmenu', function (ev) { ev.preventDefault(); });
    el.addEventListener('click', function (ev) {
        ev.preventDefault();
        if (holdFired) { holdFired = false; return; }
        if (el.disabled || !canGesture()) return;
        if (tapTimer) {
            clearTimeout(tapTimer);
            tapTimer = null;
            openCustom();
            return;
        }
        tapTimer = setTimeout(function () {
            tapTimer = null;
            window.ocQuickBid();
        }, 300);
    });
}

function renderPresets(presets, myTeam) {
    const wrap  = $('ocPresetsWrap');
    const inner = $('ocPresets');
    if (!wrap || !inner) return;
    if (!presets || presets.length === 0) { wrap.style.display = 'none'; inner.innerHTML = ''; return; }

    const nextBid = myTeam.next_bid   || myTeam.effective_base || 1;
    const maxCall = myTeam.max_call   || 0;

    // Build buttons; classify each as: reachable (ok), too-low (dim), over-limit (dim)
    inner.innerHTML = presets.map(pt => {
        let cls = 'oc-preset-btn';
        let title = '';
        if (pt < nextBid) {
            cls += ' oc-preset-low';
            title = 'Below current bid';
        } else if (maxCall > 0 && pt > maxCall) {
            cls += ' oc-preset-over';
            title = 'Exceeds your max call';
        } else {
            cls += ' oc-preset-ok';
        }
        var on = (pt === nextBid) ? ' oc-preset-on' : '';
        return '<button type="button" class="'+cls+on+'" title="'+title+'" onclick="ocSetPreset('+pt+')">'+fmtU(pt)+'</button>';
    }).join('');
    wrap.style.display = 'flex';
}

// ── Render: teams strip (Live tab) ────────────────────────────────────
function renderTeamsStrip(teams, myTeamId) {
    const container = $('ocTeamsStrip');
    if (!container) return;
    container.innerHTML = '';
    if (!teams || !teams.length) { container.innerHTML = '<span style="color:var(--txt3);font-size:.8rem;padding:8px">No teams found.</span>'; return; }

    teams.forEach(t => {
        const isMine = t.id === myTeamId;
        const pct = t.total_points > 0 ? Math.round(t.remaining_points / t.total_points * 100) : 0;
        const card = document.createElement('div');
        card.className = 'oc-strip-card' + (isMine ? ' oc-strip-mine' : '');
        card.innerHTML = `
<div class="oc-strip-top">
  <img class="oc-strip-logo" src="${esc(t.logo_url)}" alt=""/>
  <span class="oc-strip-name">${esc(t.name)}</span>
  ${isMine ? '<span class="oc-strip-mine-tag">YOU</span>' : ''}
</div>
<div class="oc-strip-purse-bar"><div class="oc-strip-purse-fill" style="width:${pct}%"></div></div>
<div class="oc-strip-stats">
  <div class="oc-strip-stat"><span class="oc-strip-stat-k">Purse</span><span class="oc-strip-stat-v">${fmtU(t.remaining_points)}</span></div>
  <div class="oc-strip-stat"><span class="oc-strip-stat-k">Max call</span><span class="oc-strip-stat-v">${t.max_call>0?fmtU(t.max_call):'—'}</span></div>
  <div class="oc-strip-stat"><span class="oc-strip-stat-k">Squad</span><span class="oc-strip-stat-v">${t.player_count||0} / ${t.max_players||'?'}</span></div>
</div>
<span class="oc-strip-badge ${t.can_bid?'oc-strip-badge-ok':'oc-strip-badge-no'}">
  ${t.can_bid ? '✅ Can Bid' : '🚫 '+esc(t.can_bid_reason||'Cannot bid')}
</span>`;
        card.addEventListener('click', () => ocOpenSquadSheet(t));
        container.appendChild(card);
    });
}

// ── Render: teams full (Teams tab) — Bid Summary structure, owner theme ──
const OCB_EYE = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';

function ocbMetrics(t) {
    const total = Number(t.total_points) || 0;
    const rem = Number(t.remaining_points) || 0;
    const pct = total > 0 ? Math.floor(rem * 100 / total) : 0;
    const purseCls = pct >= 60 ? 'pf-high' : (pct >= 30 ? 'pf-mid' : (pct >= 10 ? 'pf-low' : 'pf-crit'));
    const st = pct >= 60 ? ['COMFORTABLE', 'comfortable']
        : (pct >= 40 ? ['HEALTHY', 'healthy']
        : (pct >= 25 ? ['BALANCED', 'balanced']
        : (pct >= 10 ? ['TIGHT', 'tight'] : ['CRITICAL', 'critical'])));
    const maxPlayers = Number(t.max_players) || 0;
    const have = Number(t.player_count) || 0;
    const need = Math.max(maxPlayers - have, 0);
    const maxCall = Number(t.max_call) || 0;
    const share = rem > 0 ? Math.floor(maxCall * 100 / rem) : 100;
    const heat = (need <= 1 || share <= 15) ? 'mb-crit' : ((need <= 3 || share <= 30) ? 'mb-tight' : 'mb-ok');
    return {
        pct: pct, purseCls: purseCls, statusLabel: st[0], statusCls: st[1],
        need: need, squad: have + ' / ' + (maxPlayers || '?'), squadCompact: have + '/' + (maxPlayers || '?'),
        purse: fmtU(rem), maxBid: maxCall > 0 ? fmtU(maxCall) : '—', heat: heat,
    };
}

function ocbLogo(t, cls, fbCls) {
    return t.logo_url
        ? '<img class="' + cls + '" src="' + esc(t.logo_url) + '" alt="" loading="lazy"/>'
        : '<span class="' + fbCls + '">' + esc((t.name || '').charAt(0)) + '</span>';
}

function ocbTeamsHtml(teams, myTeamId, view) {
    const rowsTable = [], cards = [], mobs = [];
    teams.forEach(t => {
        const m = ocbMetrics(t);
        const mine = t.id === myTeamId;
        const you = mine ? '<span class="ocb-you">YOU</span>' : '';
        const eye = '<button type="button" class="ocb-eye" title="View squad" aria-label="View squad" data-team-id="' + t.id + '">' + OCB_EYE + '</button>';
        const badge = '<span class="ocb-badge ' + m.statusCls + '">' + m.statusLabel + '</span>';
        const bar = '<div class="ocb-progress"><div class="ocb-progress-fill ' + m.purseCls + '" style="width:' + m.pct + '%"></div></div>';
        const pctLbl = '<div class="ocb-pct">' + m.pct + '% remaining</div>';
        const mgr = esc(t.manager || 'Team Manager');

        rowsTable.push(
'<tr class="ocb-row' + (mine ? ' ocb-mine' : '') + '" data-team-id="' + t.id + '">' +
  '<td><div class="ocb-team-cell">' + ocbLogo(t, 'ocb-logo', 'ocb-logo-fb') +
    '<div class="ocb-team-copy"><div class="ocb-team-name">' + esc(t.name) + you + '</div><div class="ocb-manager">' + mgr + '</div></div></div></td>' +
  '<td><div class="ocb-purse-stack"><span class="ocb-purse-value">' + m.purse + '</span>' + bar + pctLbl + '</div></td>' +
  '<td><div class="ocb-needed"><span class="ocb-needed-n">' + m.need + '</span><span class="ocb-chip-label">players</span></div></td>' +
  '<td><div class="ocb-maxbid ' + m.heat + '"><span class="ocb-maxbid-lbl">MAX BID</span><span class="ocb-maxbid-val">' + m.maxBid + '</span><span class="ocb-maxbid-hint">can bid up to</span></div></td>' +
  '<td><div class="ocb-squad"><span class="ocb-squad-val">' + m.squad + '</span><span class="ocb-chip-label">recruited</span></div></td>' +
  '<td>' + badge + '</td>' +
  '<td class="ocb-access">' + eye + '</td>' +
'</tr>');

        cards.push(
'<div class="ocb-card' + (mine ? ' ocb-mine' : '') + '" data-team-id="' + t.id + '">' +
  '<div class="ocb-card-accent"></div><div class="ocb-card-body">' +
  '<div class="ocb-card-head"><div class="ocb-team-cell">' + ocbLogo(t, 'ocb-card-logo', 'ocb-card-logo ocb-logo-fallback') +
    '<div class="ocb-card-copy"><div class="ocb-card-name">' + esc(t.name) + '</div><div class="ocb-card-manager">' + mgr + you + '</div></div></div></div>' +
  '<div class="ocb-card-purse"><div class="ocb-overline">Purse Remaining</div>' +
    '<div class="ocb-card-purse-line"><span class="ocb-card-purse-value">' + m.purse + '</span></div>' + bar +
    '<div class="ocb-pct-label">' + m.pct + '% remaining</div></div>' +
  '<div class="ocb-card-stats">' +
    '<div class="ocb-stat-col"><div class="ocb-stat-label">Players Needed</div><div class="ocb-stat-figure">' + m.need + '</div></div>' +
    '<div class="ocb-stat-col ocb-stat-col--maxbid ' + m.heat + '"><div class="ocb-stat-label">Max Bid</div><div class="ocb-stat-figure"><span>' + m.maxBid + '</span></div></div>' +
    '<div class="ocb-stat-col"><div class="ocb-stat-label">Squad</div><div class="ocb-stat-figure">' + m.squad + '</div></div>' +
  '</div>' +
  '<div class="ocb-card-foot"><span class="ocb-badge ocb-card-status ' + m.statusCls + '">' + m.statusLabel + '</span>' +
    '<div class="ocb-access-actions">' + eye + '</div></div>' +
  '</div></div>');

        mobs.push(
'<div class="ocb-mob-row' + (mine ? ' ocb-mine' : '') + '" data-team-id="' + t.id + '">' +
  '<div class="ocb-mob-head">' + ocbLogo(t, 'ocb-mob-logo', 'ocb-logo-fb') +
    '<div class="ocb-mob-copy"><div class="ocb-mob-name">' + esc(t.name) + you + '</div><div class="ocb-mob-manager">' + mgr + '</div></div>' + badge + '</div>' +
  '<div class="ocb-mob-purse"><span class="ocb-mob-pts">' + m.purse + '</span>' +
    '<div class="ocb-mob-bar">' + bar + '<div class="ocb-pct">' + m.pct + '% remaining</div></div></div>' +
  '<div class="ocb-mob-stats">' +
    '<div class="ocb-mob-stat"><span class="ocb-mob-lbl">Need</span><span class="ocb-mob-val">' + m.need + '</span></div>' +
    '<div class="ocb-mob-stat ocb-mob-maxbid ' + m.heat + '"><span class="ocb-mob-lbl">Max Bid</span><span class="ocb-mob-val">' + m.maxBid + '</span></div>' +
    '<div class="ocb-mob-stat"><span class="ocb-mob-lbl">Squad</span><span class="ocb-mob-val">' + m.squadCompact + '</span></div>' +
  '</div>' +
  '<div class="ocb-mob-foot">' + eye + '</div>' +
'</div>');
    });

    return '' +
'<div class="ocb-toolbar">' +
  '<div class="ocb-toggle" role="tablist" aria-label="View toggle">' +
    '<button type="button" class="ocb-toggle-btn' + (view === 'grid' ? ' active' : '') + '" data-view="grid" aria-pressed="' + (view === 'grid') + '">GRID</button>' +
    '<button type="button" class="ocb-toggle-btn' + (view === 'list' ? ' active' : '') + '" data-view="list" aria-pressed="' + (view === 'list') + '">LIST</button>' +
  '</div>' +
'</div>' +
'<div class="ocb-panel ocb-list" style="' + (view === 'list' ? '' : 'display:none') + '"><div class="ocb-table-wrap"><table class="ocb-table"><thead><tr>' +
  '<th>Team</th><th>Purse</th><th>Needed</th><th>Max Bid</th><th>Squad</th><th>Status</th><th class="ocb-access" aria-label="View"></th>' +
'</tr></thead><tbody>' + rowsTable.join('') + '</tbody></table></div></div>' +
'<div class="ocb-panel ocb-gridwrap" style="' + (view === 'grid' ? '' : 'display:none') + '"><div class="ocb-grid">' + cards.join('') + '</div></div>' +
'<div class="ocb-mobile">' + mobs.join('') + '</div>';
}

function renderTeamsFull(force) {
    const container = $('ocTeamsFull');
    if (!container) return;
    const { teams, myTeam } = S;
    if (!teams.length) { container.innerHTML = '<div class="oc-empty-state">No teams found.</div>'; S._teamsSig = ''; return; }

    let view = 'grid';
    try { view = window.localStorage.getItem('ocTeamsView') === 'list' ? 'list' : 'grid'; } catch (e) {}
    const myTeamId = myTeam && myTeam.id;
    // Skip DOM work when nothing visible changed (polling runs every few seconds).
    const sig = view + '|' + myTeamId + '|' + teams.map(t =>
        [t.id, t.remaining_points, t.total_points, t.max_call, t.player_count, t.max_players, t.name, t.logo_url].join(':')
    ).join(',');
    if (!force && sig === S._teamsSig) return;
    S._teamsSig = sig;
    container.classList.add('ocb-root');
    container.innerHTML = ocbTeamsHtml(teams, myTeamId, view);
}

// One delegated handler: view toggle + squad sheet (eye / row / card tap).
(function () {
    document.addEventListener('click', function (ev) {
        const root = ev.target.closest && ev.target.closest('#ocTeamsFull');
        if (!root) return;
        const toggle = ev.target.closest('.ocb-toggle-btn');
        if (toggle) {
            try { window.localStorage.setItem('ocTeamsView', toggle.getAttribute('data-view') === 'list' ? 'list' : 'grid'); } catch (e) {}
            renderTeamsFull(true);
            return;
        }
        const holder = ev.target.closest('[data-team-id]');
        if (!holder) return;
        const id = parseInt(holder.getAttribute('data-team-id'), 10);
        const team = (S.teams || []).find(t => t.id === id);
        if (team) ocOpenSquadSheet(team);
    });
})();

// ── Render: my squad ──────────────────────────────────────────────────
function renderMySquad() {
    const myTeam = S.myTeam;
    const banner = $('ocMySquadBanner');
    const list   = $('ocMySquadList');
    const countEl = $('ocMySquadCount');

    if (!myTeam) {
        if (banner) banner.style.display = 'none';
        if (list) list.innerHTML = '<div class="oc-empty-state">No team assigned to your account.</div>';
        return;
    }
    if (banner) banner.style.display = '';
    src('ocMySquadLogo', myTeam.logo_url);
    txt('ocMySquadTeam', myTeam.name);
    txt('ocMySquadPurse', fmt(myTeam.remaining_points)+' / '+fmtU(myTeam.total_points)+' remaining');

    const squad = myTeam.squad || [];
    if (countEl) countEl.innerHTML = `<div class="oc-squad-count-n">${squad.length}</div><div class="oc-squad-count-lbl">Players</div>`;

    if (!list) return;
    if (!squad.length) { list.innerHTML='<div class="oc-empty-state">No players acquired yet.</div>'; return; }
    list.innerHTML = squad.map(p => `
<div class="oc-squad-row">
  <img class="oc-squad-photo" src="${esc(p.photo_url)}" alt=""/>
  <div class="oc-squad-info">
    <div class="oc-squad-name">${esc(up(p.name))}</div>
    <div class="oc-squad-chips">
      ${p.role ? `<span class="oc-squad-role">${esc(up(p.role))}</span>` : ''}
      ${p.tier_name ? `<span class="oc-squad-tier" style="border-color:${esc(p.tier_color)};color:${esc(p.tier_color)}">${esc(up(p.tier_name))}</span>` : ''}
    </div>
  </div>
  <div class="oc-squad-pts">${fmtU(p.points)}</div>
</div>`).join('');
}

// ── Squad sheet ────────────────────────────────────────────────────────
window.ocOpenSquadSheet = function(team) {
    const bd = $('ocSheetBackdrop'), sh = $('ocSheet'), inn = $('ocSheetInner');
    if (!bd||!sh||!inn) return;
    const squad = team.squad || [];
    const pct = team.total_points>0?Math.round(team.remaining_points/team.total_points*100):0;
    inn.innerHTML = `
<div class="oc-sheet-head">
  <img class="oc-sheet-head-logo" src="${esc(team.logo_url)}" alt=""/>
  <div>
    <div class="oc-sheet-head-name">${esc(team.name)}</div>
    <div class="oc-sheet-head-meta">
      Purse: ${fmt(team.remaining_points)} / ${fmtU(team.total_points)} (${pct}%) &nbsp;·&nbsp;
      Max call: ${team.max_call>0?fmtU(team.max_call):'—'} &nbsp;·&nbsp;
      Squad: ${team.player_count||squad.length} / ${team.max_players||'?'}
    </div>
  </div>
</div>
<div class="oc-squad-list">
  ${squad.length===0 ? '<div class="oc-empty-state">No players yet.</div>'
    : squad.map(p=>`
<div class="oc-squad-row">
  <img class="oc-squad-photo" src="${esc(p.photo_url)}" alt=""/>
  <div class="oc-squad-info">
    <div class="oc-squad-name">${esc(up(p.name))}</div>
    <div class="oc-squad-chips">
      ${p.role?`<span class="oc-squad-role">${esc(up(p.role))}</span>`:''}
      ${p.tier_name?`<span class="oc-squad-tier" style="border-color:${esc(p.tier_color)};color:${esc(p.tier_color)}">${esc(up(p.tier_name))}</span>`:''}
    </div>
  </div>
  <div class="oc-squad-pts">${fmtU(p.points)}</div>
</div>`).join('')}
</div>`;
    bd.classList.add('oc-open'); sh.classList.add('oc-open');
};
window.ocCloseSquadSheet = function() {
    $('ocSheetBackdrop')?.classList.remove('oc-open');
    $('ocSheet')?.classList.remove('oc-open');
};

// ── Slab helpers ────────────────────────────────────────────────────────
// Returns the increment defined by the slab that covers `amount`.
// `slabs` must be sorted descending by from_amount (as the server sends them).
function slabStep(amount, slabs) {
    for (let s of slabs) {
        if (amount >= s.from_amount) return s.increment;
    }
    return 1;
}

// Snap `amount` DOWN to the nearest valid step boundary within its slab.
function snapToSlab(amount, slabs) {
    for (let s of slabs) {
        if (amount >= s.from_amount) {
            const base = s.from_amount;
            const inc  = s.increment;
            return base + Math.floor((amount - base) / inc) * inc;
        }
    }
    return amount;
}

// ── Bid input step ─────────────────────────────────────────────────────
window.ocChangeBid = function(delta) {
    const input = $('ocBidInput');
    if (!input || input.disabled) return;
    const myTeam = S.myTeam;
    if (!myTeam) return;
    let cur = parseInt(input.value, 10) || 0;
    const slabs = S.slabs;
    const effectiveBase = myTeam.effective_base || 1;

    if (delta > 0) {
        // If at or below current live bid, jump straight to the server's
        // pre-computed next_bid (already slab-correct); otherwise add one
        // slab step to whatever value the user has typed.
        if (S.player && cur <= (S.player.current_bid || 0)) {
            cur = myTeam.next_bid;
        } else {
            cur = cur + slabStep(cur, slabs);
        }
    } else {
        // Step back one slab increment, then snap to the nearest valid
        // slab boundary so the resulting value is always auction-legal.
        const step = slabStep(cur, slabs);
        const decreased = cur - step;
        cur = Math.max(effectiveBase, snapToSlab(Math.max(0, decreased), slabs));
    }
    input.value = cur;
};

// Set bid input directly from a preset button
window.ocSetPreset = function(amount) {
    if (!stageOpen(S.player)) return;
    const input = $('ocBidInput');
    if (input && !input.disabled) input.value = amount;
};

// ── Bid confirm ────────────────────────────────────────────────────────
window.ocOpenBidConfirm = function() {
    const { myTeam, player } = S;
    if (!stageOpen(player)) return;
    if (ownerTimerHeld() || (ownerBidFrozen() && !(myTeam && myTeam.is_leading))) {
        toast(ownerBidLockToast(), 'err');
        paintBidTimer();
        return;
    }
    if (!myTeam || !player) return;
    const input = $('ocBidInput');
    const amount = parseInt((input&&input.value)||'0', 10);
    if (!amount || amount < (myTeam.effective_base||1)) {
        toast('Bid must be at least '+fmtU(myTeam.effective_base), 'err'); return;
    }
    if (myTeam.max_call>0 && amount>myTeam.max_call) {
        toast('Exceeds your max call of '+fmtU(myTeam.max_call), 'err'); return;
    }
    S.pendingBid = { playerId: player.id, teamId: myTeam.id, amount };
    txt('ocConfirmPlayer', up(player.name));
    txt('ocConfirmTeam', myTeam.name);
    txt('ocConfirmPts', fmt(amount));
    const ov = $('ocBidOverlay');
    if (ov) ov.style.display='flex';
};

window.ocCancelBidConfirm = function() {
    const ov = $('ocBidOverlay');
    if (ov) ov.style.display='none';
    S.pendingBid = null;
};

window.ocSubmitBid = function() {
    const bid = S.pendingBid;
    if (!bid) return;
    const btn = $('ocBtnConfirm');
    if (btn) btn.disabled = true;
    fetch('/auction/owner/place-bid', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({jsonrpc:'2.0',method:'call',params:{
            player_id:bid.playerId, team_id:bid.teamId, bid_amount:bid.amount
        }}),
    })
    .then(r=>r.json())
    .then(resp => {
        const res = resp.result || resp;
        if (res.success) {
            toast('Bid of '+fmtU(bid.amount)+' placed! 🎯','ok');
            ocCancelBidConfirm();
            fetchData();
        } else {
            toast(res.error||'Bid failed','err');
        }
    })
    .catch(()=>toast('Network error. Please retry.','err'))
    .finally(()=>{ if(btn) btn.disabled=false; });
};

// ── Revoke last bid ────────────────────────────────────────────────────
window.ocRevokeBid = function() {
    const { myTeam, player, revoke } = S;
    if (!stageOpen(player)) return;
    if (ownerBidFrozen()) {
        toast(ownerBidLockToast(), 'err');
        return;
    }
    if (!myTeam || !player) return;
    if (!revoke || !revoke.can_revoke || revoke.remaining <= 0) {
        toast('Revoke not available', 'err'); return;
    }
    const remaining = revoke.remaining;
    if (!confirm(
        'Revoke your bid of ' + fmtU(player.current_bid) + '?\n' +
        'The bid will revert to the previous team\'s call.\n' +
        'Revokes remaining after this: ' + (remaining - 1) + '/' + revoke.max
    )) return;

    const btn = $('ocRevokeBtn');
    if (btn) btn.disabled = true;

    fetch('/auction/owner/revoke-bid', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ jsonrpc:'2.0', method:'call', params:{
            player_id: player.id,
            team_id:   myTeam.id,
        }}),
    })
    .then(r => r.json())
    .then(resp => {
        const res = resp.result || resp;
        if (res.success) {
            const msg = res.prev_team_name
                ? 'Bid revoked ✓ — ' + res.prev_team_name + ' leads with ' + fmtU(res.new_bid)
                : 'Bid revoked ✓ — player is now open for bids';
            toast(msg, 'ok');
            fetchData();
        } else {
            toast(res.error || 'Revoke failed', 'err');
            if (btn) btn.disabled = false;
        }
    })
    .catch(() => {
        toast('Network error — revoke not saved', 'err');
        if (btn) btn.disabled = false;
    });
};
function playHammerAnim(n) {
    const ex = document.querySelector('.oc-hammer-overlay');
    if (ex) ex.remove();
    const ov = document.createElement('div');
    ov.className = 'oc-hammer-overlay';
    ov.innerHTML = '<div class="oc-hammer-inner">'
        + '<div class="oc-hammer-icon">\uD83D\uDD28</div>'
        + '<div class="oc-hammer-count"></div></div>';
    document.body.appendChild(ov);
    requestAnimationFrame(() => requestAnimationFrame(() => ov.classList.add('oc-hammer-in')));

    const inner   = ov.querySelector('.oc-hammer-inner');
    const countEl = ov.querySelector('.oc-hammer-count');
    let strike = 0;

    function doStrike() {
        if (strike >= n) {
            countEl.textContent  = 'FINAL CALL!';
            countEl.className    = 'oc-hammer-count oc-hammer-final';
            setTimeout(() => {
                ov.classList.remove('oc-hammer-in');
                ov.classList.add('oc-hammer-out');
                setTimeout(() => ov.remove(), 500);
            }, 1800);
            return;
        }
        strike++;
        countEl.textContent = strike;
        countEl.className   = 'oc-hammer-count';
        void countEl.offsetHeight;
        countEl.className   = 'oc-hammer-count oc-hammer-pulse';
        const cur   = inner.querySelector('.oc-hammer-icon');
        const clone = cur.cloneNode(true);
        clone.classList.add('oc-hammer-swing');
        inner.replaceChild(clone, cur);
        setTimeout(doStrike, 900);
    }
    setTimeout(doStrike, 400);
}

function handleCounter(counter) {
    if (!counter) return;
    const ts = counter.started_at || null;
    if (!S._counterInit) {
        S._counterInit = true;
        S._counterTs   = ts;
        // Play only if the counter fired very recently (page loaded mid-auction)
        if (ts && (counter.age_seconds || 9999) < 20) {
            playHammerAnim(counter.hammer_count || 3);
        }
    } else if (ts && ts !== S._counterTs) {
        S._counterTs = ts;
        playHammerAnim(counter.hammer_count || 3);
    }
}

// ── Poll ───────────────────────────────────────────────────────────────
function fetchData() {
    fetch('/auction/owner/data', {cache:'no-store'})
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(data => {
        applyPointUnit((data.tournament && data.tournament.point_unit) || null);
        startOwnerSse(data);
        const liveBadge = $('ocLiveBadge');
        if (liveBadge) liveBadge.className = 'oc-live-badge';

        const incoming  = data.current_player || null;
        const myTeamId  = (data.my_team && data.my_team.id) || null;
        const prev      = S._lastBid;

        // Detect a rival bid: same player, bid went up, and it's NOT my team
        if (
            incoming && prev.playerId === incoming.id &&
            (incoming.current_bid || 0) > prev.bid &&
            incoming.current_bid_team &&
            incoming.current_bid_team.id !== myTeamId
        ) {
            flashRivalBid(incoming);
        }

        // Update last-bid tracker
        S._lastBid = incoming
            ? { playerId: incoming.id, bid: incoming.current_bid || 0,
                teamId: incoming.current_bid_team ? incoming.current_bid_team.id : null }
            : { playerId: null, bid: 0, teamId: null };

        updatePlayerCounts(data.player_counts, incoming && incoming.id);
        S.player  = incoming;
        S.myTeam  = data.my_team || null;
        S.owner   = data.owner || null;
        S.teams   = data.teams || [];
        paintHeaderIdentity(S.myTeam, S.owner);
        // Server sends slabs sorted descending by from_amount
        S.slabs   = data.slabs || [];
        S.presets = data.presets || [];
        S.revoke  = data.revoke  || null;
        syncBidTimer((incoming && incoming.bid_timer) || null);

        handleCounter(data.counter || null);

        renderPlayer(S.player);
        renderBidPanel(S.myTeam, S.player);
        renderRevoke();
        renderTeamsStrip(S.teams, S.myTeam && S.myTeam.id);
        renderTeamsFull();
        renderMySquad();
    })
    .catch(() => {
        const liveBadge = $('ocLiveBadge');
        if (liveBadge) liveBadge.className = 'oc-live-badge oc-offline';
    });
}

// ── Cross-tab refresh ──────────────────────────────────────────────────
window.addEventListener('storage', e => {
    if (e.key === 'auction:player_sold') {
        // Show SOLD overlay immediately with the team/pts info from the event
        try {
            const soldData = e.newValue ? JSON.parse(e.newValue) : null;
            if (soldData) showSoldOverlay(soldData);
            if (S.player) S.player.state = 'sold';
            closeOwnerBids();
        } catch (_) {}
        // Rapid-poll burst to detect the next player quickly (same pattern as live-board)
        fetchData();
        let burstCount = 0;
        const burstId = setInterval(() => {
            fetchData();
            if (++burstCount >= 5) clearInterval(burstId);
        }, 1500);
    }
});

// ── Players board: Sold / Unsold / In auction ──────────────────────────
const PB = { bucket: 'sold', offset: 0, total: 0, q: '', open: false, busy: false, seq: 0, myTeamId: 0, sig: '' };
const PB_TITLES = { sold: 'Sold players', unsold: 'Unsold players', auction: 'In auction' };
const PB_PAGE = 20;

function updatePlayerCounts(c, stageId) {
    c = c || {};
    const sold = c.sold || 0, unsold = c.unsold || 0, auction = c.auction || 0;
    const set = (id, v) => { const el = $(id); if (el && el.textContent !== String(v)) el.textContent = v; };
    set('ocPcSold', sold); set('ocPcUnsold', unsold); set('ocPcAuction', auction);
    // Re-pull the open list only when the counts actually moved (no polling).
    const sig = sold + '/' + unsold + '/' + auction + '/' + (stageId || 0);
    if (PB.open && sig !== PB.sig) loadPlayers(true);
    PB.sig = sig;
}

function pbRow(p) {
    const mine = PB.myTeamId && p.team_id === PB.myTeamId;
    const photo = p.photo_url
        ? '<img class="oc-pb-photo" src="' + esc(p.photo_url) + '" alt="" loading="lazy"/>'
        : '<span class="oc-pb-photo oc-pb-photo-fb">' + esc((p.name || '?').charAt(0)) + '</span>';
    let foot = '';
    if (PB.bucket === 'sold') {
        foot = '<div class="oc-pb-team">' +
            (p.team_logo_url ? '<img src="' + esc(p.team_logo_url) + '" alt="" loading="lazy"/>' : '') +
            '<span>' + esc(p.team_name || '') + '</span></div>' +
            '<div class="oc-pb-price">' + fmtU(p.points) + '</div>';
    } else {
        foot = (p.on_stage ? '<div class="oc-pb-stage">ON STAGE</div>' : '<div class="oc-pb-base-lbl">Base</div>') +
            '<div class="oc-pb-price">' + fmtU(p.base_price) + '</div>';
    }
    const attrs = (p.attrs || []).map(a =>
        '<div class="oc-pb-attr"><span>' + esc(a.k) + '</span><b>' + esc(a.v) + '</b></div>').join('');
    const live = PB.bucket === 'auction' && p.on_stage;
    return '<div class="oc-pb-card' + (mine ? ' oc-pb-mine' : '') + (live ? ' oc-pb-live' : '') + '">' +
        '<div class="oc-pb-ctop">' + photo +
        '<div class="oc-pb-info"><div class="oc-pb-name">' + esc(p.name) + '</div>' +
        '<div class="oc-pb-sub">' + (p.sl_no ? '<span class="oc-pb-sl">#' + p.sl_no + '</span>' : '') +
        (p.role ? '<span class="oc-pb-role">' + esc(up(p.role)) + '</span>' : '') + '</div></div></div>' +
        (attrs ? '<div class="oc-pb-attrs">' + attrs + '</div>' : '') +
        '<div class="oc-pb-cfoot">' + foot + '</div></div>';
}

function loadPlayers(reset) {
    if (reset) PB.offset = 0;
    const mySeq = ++PB.seq;
    PB.busy = true;
    const list = $('ocPbList'), more = $('ocPbMore');
    if (reset && list && !list.children.length) list.innerHTML = '<div class="oc-empty-state">Loading…</div>';
    const url = '/auction/owner/players?bucket=' + encodeURIComponent(PB.bucket) +
        '&offset=' + PB.offset + '&limit=' + PB_PAGE + '&q=' + encodeURIComponent(PB.q);
    fetch(url, { cache: 'no-store' })
        .then(r => r.ok ? r.json() : Promise.reject(r.status))
        .then(d => {
            if (mySeq !== PB.seq) return;   // stale response
            PB.busy = false;
            PB.myTeamId = d.my_team_id || 0;
            PB.total = d.total || 0;
            const rows = (d.players || []).map(pbRow).join('');
            if (reset) list.innerHTML = rows || '<div class="oc-empty-state">No players found.</div>';
            else list.insertAdjacentHTML('beforeend', rows);
            PB.offset = (d.offset || 0) + (d.players || []).length;
            more.style.display = PB.offset < PB.total ? '' : 'none';
        })
        .catch(() => {
            if (mySeq !== PB.seq) return;
            PB.busy = false;
            if (reset) list.innerHTML = '<div class="oc-empty-state">Could not load players.</div>';
        });
}

window.ocOpenPlayers = function (bucket) {
    if (PB.bucket !== bucket) { PB.q = ''; const si = $('ocPbSearch'); if (si) si.value = ''; }
    PB.bucket = bucket;
    PB.open = true;
    $('ocPbTitle').textContent = PB_TITLES[bucket] || 'Players';
    document.querySelectorAll('.oc-pb-tabs button, .oc-pc').forEach(b =>
        b.classList.toggle('active', b.getAttribute('data-bucket') === bucket));
    $('ocPbBackdrop').classList.add('oc-open');
    $('ocPb').classList.add('oc-open');
    $('ocPbList').innerHTML = '';
    loadPlayers(true);
};
window.ocClosePlayers = function () {
    PB.open = false; PB.seq++;
    $('ocPbBackdrop').classList.remove('oc-open');
    $('ocPb').classList.remove('oc-open');
    document.querySelectorAll('.oc-pc').forEach(b => b.classList.remove('active'));
};
window.ocPlayersMore = function () { if (!PB.busy) loadPlayers(false); };
(function () {
    let timer = null;
    document.addEventListener('input', function (ev) {
        if (ev.target && ev.target.id === 'ocPbSearch') {
            clearTimeout(timer);
            timer = setTimeout(function () { PB.q = ev.target.value.trim(); loadPlayers(true); }, 300);
        }
    });
    document.addEventListener('keydown', function (ev) {
        if (ev.key === 'Escape' && PB.open) window.ocClosePlayers();
    });
})();

// ── Squad Snapshot ─────────────────────────────────────────────────────
window.ocSquadSnapshot = function(mode, btn) {
    const myTeam = S.myTeam;
    if (!myTeam) { toast('No team data available', 'err'); return; }
    const squad = myTeam.squad || [];
    if (!squad.length) { toast('No players in squad yet', 'err'); return; }

    const isLaptop = mode === 'laptop';
    const W        = isLaptop ? 900 : 390;

    // Accent colour from theme
    const themeColors = {
        pistah:       { c: '#7c3aed', cl: '#a78bfa' },
        strawberry:   { c: '#e91e8c', cl: '#f472b6' },
        butterscotch: { c: '#d97706', cl: '#fbbf24' },
        cherry:       { c: '#dc2626', cl: '#f87171' },
    };
    const theme  = document.body.getAttribute('data-theme') || 'vanilla';
    const { c: ac, cl: acl } = themeColors[theme] || { c: '#2252b5', cl: '#58a6ff' };

    const tournName = (document.querySelector('.oc-header-tourn') || {}).textContent?.trim() || '';
    const fmtN  = n  => (n || 0).toLocaleString();
    const esc   = s  => String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    const imgEl = (src, w, style) =>
        `<img src="${esc(src)}" crossorigin="anonymous" style="width:${w}px;height:${w}px;${style}object-fit:cover;background:#1d2438;" onerror="this.style.opacity='.3'"/>`;

    // ── Player cards ────────────────────────────────────────────────────
    const chipStyle = (color, bg) =>
        `display:inline-block;border-radius:5px;padding:2px 8px;font-size:.66rem;font-weight:600;background:${bg};color:${color};`;

    const playerCard = isLaptop
        ? p => `
<div style="background:#111520;border:1px solid rgba(255,255,255,.08);border-radius:12px;padding:16px 12px;display:flex;flex-direction:column;align-items:center;gap:8px;text-align:center;">
  ${imgEl(p.photo_url, 68, `border-radius:50%;border:2.5px solid ${ac};`)}
  <div style="font-size:.86rem;font-weight:700;color:#e8edf8;line-height:1.25;">${esc(up(p.name))}</div>
  <div style="display:flex;gap:5px;flex-wrap:wrap;justify-content:center;">
    ${p.role      ? `<span style="${chipStyle(acl, 'rgba(255,255,255,.08)')}">${esc(up(p.role))}</span>`       : ''}
    ${p.tier_name ? `<span style="${chipStyle(p.tier_color || acl, 'transparent')}border:1px solid ${esc(p.tier_color || ac)};">${esc(up(p.tier_name))}</span>` : ''}
  </div>
  <div style="font-size:.95rem;font-weight:800;color:${acl};">${window.fmtUnit?window.fmtUnit(p.points):fmtN(p.points)+' pts'}</div>
</div>`
        : p => `
<div style="background:#111520;border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:10px 13px;display:flex;align-items:center;gap:12px;">
  ${imgEl(p.photo_url, 44, `border-radius:50%;border:2px solid ${ac};flex-shrink:0;`)}
  <div style="flex:1;min-width:0;">
    <div style="font-size:.86rem;font-weight:700;color:#e8edf8;">${esc(up(p.name))}</div>
    <div style="display:flex;gap:5px;margin-top:4px;flex-wrap:wrap;">
      ${p.role      ? `<span style="${chipStyle(acl, 'rgba(255,255,255,.08)')}">${esc(up(p.role))}</span>`       : ''}
      ${p.tier_name ? `<span style="${chipStyle(p.tier_color || acl, 'transparent')}border:1px solid ${esc(p.tier_color || ac)};">${esc(up(p.tier_name))}</span>` : ''}
    </div>
  </div>
  <div style="font-size:.86rem;font-weight:800;color:${acl};flex-shrink:0;">${window.fmtUnit?window.fmtUnit(p.points):fmtN(p.points)+' pts'}</div>
</div>`;

    const cardsHtml = isLaptop
        ? `<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px;padding:22px 24px;">${squad.map(playerCard).join('')}</div>`
        : `<div style="padding:14px 15px;display:flex;flex-direction:column;gap:9px;">${squad.map(playerCard).join('')}</div>`;

    // ── Full card ────────────────────────────────────────────────────────
    const card = `
<div style="background:#0a0d14;width:${W}px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;border-radius:16px;overflow:hidden;">
  <div style="height:4px;background:linear-gradient(90deg,${ac},${acl},${ac});"></div>
  <div style="background:linear-gradient(135deg,#161c2c 0%,#0d1320 100%);padding:${isLaptop ? '22px 28px' : '16px 18px'};display:flex;align-items:center;gap:${isLaptop ? '18px' : '14px'};border-bottom:1px solid rgba(255,255,255,.07);">
    ${imgEl(myTeam.logo_url, isLaptop ? 68 : 54, `border-radius:50%;border:3px solid ${ac};flex-shrink:0;`)}
    <div style="flex:1;min-width:0;">
      <div style="font-size:${isLaptop ? '1.2rem' : '1rem'};font-weight:800;color:#e8edf8;">${esc(myTeam.name)}</div>
      ${tournName ? `<div style="font-size:.7rem;color:${acl};margin-top:2px;font-weight:600;letter-spacing:.04em;">${esc(tournName)}</div>` : ''}
      <div style="font-size:.74rem;color:#8899bb;margin-top:4px;">${fmtN(myTeam.remaining_points)} / ${window.fmtUnit?window.fmtUnit(myTeam.total_points):fmtN(myTeam.total_points)+' pts'} remaining</div>
    </div>
    <div style="background:rgba(255,255,255,.05);border:1.5px solid ${ac};border-radius:12px;padding:${isLaptop ? '12px 20px' : '9px 14px'};text-align:center;flex-shrink:0;">
      <div style="font-size:${isLaptop ? '1.8rem' : '1.4rem'};font-weight:900;color:${acl};line-height:1;">${squad.length}</div>
      <div style="font-size:.6rem;color:#8899bb;letter-spacing:.1em;margin-top:2px;">PLAYERS</div>
    </div>
  </div>
  ${cardsHtml}
  <div style="padding:8px 16px 14px;text-align:center;">
    <span style="font-size:.6rem;color:rgba(255,255,255,.2);letter-spacing:.12em;font-weight:600;">AUCTION CHAMP</span>
  </div>
</div>`;

    // ── Render off-screen and capture ────────────────────────────────────
    const wrap = document.createElement('div');
    wrap.style.cssText = `position:fixed;left:-9999px;top:0;width:${W}px;z-index:-1;`;
    wrap.innerHTML = card;
    document.body.appendChild(wrap);
    void wrap.offsetHeight;

    const origHtml = btn ? btn.innerHTML : '';
    if (btn) { btn.innerHTML = '&#x23F3;'; btn.disabled = true; }

    html2canvas(wrap.firstElementChild, {
        scale:           2,
        backgroundColor: '#0a0d14',
        useCORS:         true,
        allowTaint:      false,
        logging:         false,
        imageTimeout:    8000,
    }).then(function(canvas) {
        document.body.removeChild(wrap);
        if (btn) { btn.innerHTML = origHtml; btn.disabled = false; }
        const ts   = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        const name = (myTeam.name || 'squad').replace(/\s+/g, '_');
        const link = document.createElement('a');
        link.href     = canvas.toDataURL('image/png');
        link.download = `${name}_${mode}_${ts}.png`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        toast('Snapshot saved! &#x1F4F8;', 'ok');
    }).catch(function(err) {
        document.body.removeChild(wrap);
        if (btn) { btn.innerHTML = origHtml; btn.disabled = false; }
        console.error('Squad snapshot error:', err);
        toast('Snapshot failed — check console', 'err');
    });
};

// ── Boot ───────────────────────────────────────────────────────────────
function projectorSseUrl(data) {
    var t = (data && data.tournament) || {};
    var db = t.db_name || document.body.getAttribute('data-db') || '';
    var slug = t.slug || document.body.getAttribute('data-slug') || '';
    if (!db || !slug) return '';
    return '/' + db + '/auction/projector/' + slug + '/events';
}
function bidTimerUrl() {
    var db = (document.body && document.body.getAttribute('data-db')) || '';
    var qs = [];
    if (S.player && S.player.id) qs.push('player_id=' + encodeURIComponent(S.player.id));
    var path = (db ? '/' + db : '') + '/auction/bid_timer';
    return qs.length ? path + '?' + qs.join('&') : path;
}
function pollBidTimer() {
    fetch(bidTimerUrl(), {cache: 'no-store', credentials: 'same-origin'})
        .then(function (r) { return r.ok ? r.json() : Promise.reject(r.status); })
        .then(syncBidTimer)
        .catch(function () {});
}
function startBidTimerPoll() {
    if (!S._bidTimerPoll) S._bidTimerPoll = setInterval(pollBidTimer, 1000);
}
function startHttpPoll() {
    if (!S.pollTimer) S.pollTimer = setInterval(fetchData, 3000);
}
function stopHttpPoll() {
    if (S.pollTimer) { clearInterval(S.pollTimer); S.pollTimer = null; }
}
function startOwnerSse(data) {
    if (S._sseStarted) return;
    var url = projectorSseUrl(data);
    if (!url || typeof EventSource === 'undefined') {
        startHttpPoll();
        return;
    }
    S._sseStarted = true;
    var es;
    try { es = new EventSource(url); }
    catch (e) { startHttpPoll(); return; }
    function onEvt() {
        stopHttpPoll();
        fetchData();
    }
    es.addEventListener('snapshot', onEvt);
    es.addEventListener('auction.update', onEvt);
    es.onopen = function () { stopHttpPoll(); };
    es.onerror = function () { startHttpPoll(); };
}

window.ocAskLogout = function () {
    show('ocLogoutOverlay', true);
};
window.ocCancelLogout = function () {
    show('ocLogoutOverlay', false);
};
window.ocConfirmLogout = function () {
    window.location.href = '/web/session/logout?redirect=/web/login';
};

document.addEventListener('DOMContentLoaded', () => {
    var logoutBtn = $('ocLogoutBtn');
    if (logoutBtn) logoutBtn.addEventListener('click', window.ocAskLogout);
    bindBidGestures($('ocRaiseBtn'));
    bindBidGestures($('ocCurrentBidBox'));
    fetchData();
    startOwnerSse();
    startBidTimerPoll();
    window._auctionOcFetch = fetchData;
});

})();
