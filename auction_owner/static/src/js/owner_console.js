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
    // Track last known bid to detect rival changes between polls
    _lastBid: { playerId: null, bid: 0, teamId: null },
};

// ── Tiny helpers ───────────────────────────────────────────────────────
const $ = id => document.getElementById(id);
const esc = s => (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
const fmt = n => (n||0).toLocaleString();
function show(id, v) { const e=$(id); if(e) e.style.display = v?'':'none'; }
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

// ── SOLD overlay ───────────────────────────────────────────────
function showSoldOverlay(soldData) {
    const overlay = $('ocSoldOverlay');
    if (!overlay) return;
    const soldTo = $('ocSoldTo');
    if (soldTo && soldData) {
        soldTo.textContent = soldData.team ? soldData.team + ' · ' + (soldData.pts || '') + ' pts' : '';
    }
    // restart stamp animation
    overlay.classList.remove('oc-sold-show');
    void overlay.offsetWidth;
    overlay.classList.add('oc-sold-show');
}

function hideSoldOverlay() {
    const overlay = $('ocSoldOverlay');
    if (overlay) overlay.classList.remove('oc-sold-show');
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
    const amount   = fmt(player.current_bid);

    // 1. Slide-in alert banner inside the showcase card
    const alertEl = $('ocRivalAlert');
    const msgEl   = $('ocRivalMsg');
    if (alertEl && msgEl) {
        msgEl.textContent = teamName + ' raised to ' + amount + ' pts!';
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
    toast('🔥 ' + teamName + ' — ' + amount + ' pts!', 'warn');

    // 4. Haptic feedback on mobile (two short buzzes)
    if (navigator.vibrate) navigator.vibrate([80, 60, 80]);
}

// ── Render: player showcase ────────────────────────────────────────────
function renderPlayer(p) {
    if (!p) {
        show('ocWaiting', true); show('ocPlayerWrap', false);
        hideSoldOverlay();
        return;
    }
    show('ocWaiting', false); show('ocPlayerWrap', true);

    // Show SOLD overlay when player is confirmed sold; hide it for all other states
    // (actual auction states are 'draft', 'auction', 'sold', 'unsold' — not 'available'/'on_stage')
    if (p.state === 'sold') {
        showSoldOverlay(null);
    } else {
        hideSoldOverlay();
    }

    src('ocPlayerPhoto', p.photo_url);
    txt('ocPlayerName', p.name);
    txt('ocPlayerRole', p.role || '—');

    const styleEl = $('ocPlayerStyle');
    if (styleEl) {
        const parts = [p.batting_style, p.bowling_style].filter(Boolean);
        styleEl.textContent = parts.join(' · ');
        styleEl.style.display = parts.length ? '' : 'none';
    }

    const pill = $('ocTierPill');
    if (pill) { pill.textContent = p.tier_name || '—'; pill.style.background = p.tier_color || ''; }

    const ring = $('ocPhotoRing');
    if (ring) ring.style.background = p.tier_color ? `conic-gradient(${p.tier_color},#fff3,${p.tier_color})` : '';

    txt('ocSlNo', p.sl_no ? '#' + p.sl_no : '');
    txt('ocBasePrice', p.base_price ? fmt(p.base_price)+' pts' : '—');
    txt('ocCurrentBid', p.current_bid ? fmt(p.current_bid)+' pts' : 'No bids yet');

    const hasLeader = p.current_bid_team && p.current_bid_team.name;
    show('ocLeadingTeam', !!hasLeader);
    if (hasLeader) {
        src('ocLeadingLogo', p.current_bid_team.logo_url);
        txt('ocLeadingName', p.current_bid_team.name);
    }
}

// ── Render: bid panel ──────────────────────────────────────────────────
function renderBidPanel(myTeam, player) {
    if (!myTeam || !player) { show('ocBidPanel', false); return; }
    show('ocBidPanel', true);

    src('ocMyTeamLogo', myTeam.logo_url);
    txt('ocMyTeamName', myTeam.name);

    const pct = myTeam.total_points > 0 ? (myTeam.remaining_points / myTeam.total_points * 100) : 0;
    const barFill = $('ocMyPurseBar');
    if (barFill) barFill.style.width = pct + '%';
    txt('ocMyPurse', fmt(myTeam.remaining_points)+' / '+fmt(myTeam.total_points)+' pts');

    txt('ocMaxCallVal', myTeam.max_call > 0 ? fmt(myTeam.max_call)+' pts' : '—');

    const input   = $('ocBidInput');
    const bidBtn  = $('ocBidCta');
    const reasonEl = $('ocBidReason');

    if (!myTeam.can_bid) {
        if (input) { input.disabled = true; input.value = ''; }
        if (bidBtn) bidBtn.disabled = true;
        if (reasonEl) { reasonEl.textContent = '🚫 '+( myTeam.can_bid_reason || 'Cannot bid'); reasonEl.className='oc-bid-reason oc-reason-err'; }
        renderPresets([], myTeam);  // hide preset wrap when can't bid
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
            reasonEl.textContent = myTeam.max_call > 0 ? 'Max call for this player: '+fmt(myTeam.max_call)+' pts' : '';
            reasonEl.className = 'oc-bid-reason oc-reason-ok';
        }
        renderPresets(S.presets, myTeam);
    }
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
        return '<button class="'+cls+'" title="'+title+'" onclick="ocSetPreset('+pt+')">'+fmt(pt)+'</button>';
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
  <div class="oc-strip-stat"><span class="oc-strip-stat-k">Purse</span><span class="oc-strip-stat-v">${fmt(t.remaining_points)} pts</span></div>
  <div class="oc-strip-stat"><span class="oc-strip-stat-k">Max call</span><span class="oc-strip-stat-v">${t.max_call>0?fmt(t.max_call)+' pts':'—'}</span></div>
  <div class="oc-strip-stat"><span class="oc-strip-stat-k">Squad</span><span class="oc-strip-stat-v">${t.player_count||0} / ${t.max_players||'?'}</span></div>
</div>
<span class="oc-strip-badge ${t.can_bid?'oc-strip-badge-ok':'oc-strip-badge-no'}">
  ${t.can_bid ? '✅ Can Bid' : '🚫 '+esc(t.can_bid_reason||'Cannot bid')}
</span>`;
        card.addEventListener('click', () => ocOpenSquadSheet(t));
        container.appendChild(card);
    });
}

// ── Render: teams full (Teams tab) ────────────────────────────────────
function renderTeamsFull() {
    const container = $('ocTeamsFull');
    if (!container) return;
    const { teams, myTeam, player } = S;
    if (!teams.length) { container.innerHTML = '<div class="oc-empty-state">No teams found.</div>'; return; }

    const myTeamId = myTeam && myTeam.id;
    container.innerHTML = '';
    teams.forEach(t => {
        const isMine = t.id === myTeamId;
        const pct = t.total_points > 0 ? Math.round(t.remaining_points / t.total_points * 100) : 0;
        const card = document.createElement('div');
        card.className = 'oc-team-full-card' + (isMine ? ' oc-mine-card' : '');
        card.innerHTML = `
<div class="oc-team-card-head">
  <img class="oc-team-card-logo" src="${esc(t.logo_url)}" alt=""/>
  <div class="oc-team-card-main">
    <div class="oc-team-card-name">${esc(t.name)} ${isMine?'<span class="oc-mine-tag">MY TEAM</span>':''}</div>
    <div class="oc-team-card-mgr">${esc(t.manager||'')}</div>
  </div>
  <div class="oc-team-card-squad-count">
    ${t.player_count||0} / ${t.max_players||'?'}
    <div class="oc-squad-fraction">players</div>
  </div>
</div>
<div class="oc-team-card-body">
  <div class="oc-budget-row">
    <div class="oc-budget-bar-bg"><div class="oc-budget-bar-fill" style="width:${pct}%"></div></div>
    <div class="oc-budget-text">${fmt(t.remaining_points)} / ${fmt(t.total_points)} pts</div>
  </div>
  <div class="oc-team-stats-row">
    <span class="oc-stat-pill"><span class="oc-stat-pill-icon">💰</span> Max call: ${t.max_call>0?fmt(t.max_call)+' pts':'—'}</span>
    ${player?`<span class="oc-stat-pill"><span class="oc-stat-pill-icon">⬆️</span> Next bid: ${fmt(t.next_bid)} pts</span>`:''}
  </div>
  <div class="oc-can-bid-row">
    <span class="oc-can-bid-chip ${t.can_bid?'oc-chip-ok':'oc-chip-no'}">
      ${t.can_bid ? '✅ Can bid this round' : '🚫 '+esc(t.can_bid_reason||'Cannot bid')}
    </span>
  </div>
</div>`;
        card.addEventListener('click', () => ocOpenSquadSheet(t));
        container.appendChild(card);
    });
}

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
    txt('ocMySquadPurse', fmt(myTeam.remaining_points)+' / '+fmt(myTeam.total_points)+' pts remaining');

    const squad = myTeam.squad || [];
    if (countEl) countEl.innerHTML = `<div class="oc-squad-count-n">${squad.length}</div><div class="oc-squad-count-lbl">Players</div>`;

    if (!list) return;
    if (!squad.length) { list.innerHTML='<div class="oc-empty-state">No players acquired yet.</div>'; return; }
    list.innerHTML = squad.map(p => `
<div class="oc-squad-row">
  <img class="oc-squad-photo" src="${esc(p.photo_url)}" alt=""/>
  <div class="oc-squad-info">
    <div class="oc-squad-name">${esc(p.name)}</div>
    <div class="oc-squad-chips">
      ${p.role ? `<span class="oc-squad-role">${esc(p.role)}</span>` : ''}
      ${p.tier_name ? `<span class="oc-squad-tier" style="border-color:${esc(p.tier_color)};color:${esc(p.tier_color)}">${esc(p.tier_name)}</span>` : ''}
    </div>
  </div>
  <div class="oc-squad-pts">${fmt(p.points)} pts</div>
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
      Purse: ${fmt(team.remaining_points)} / ${fmt(team.total_points)} pts (${pct}%) &nbsp;·&nbsp;
      Max call: ${team.max_call>0?fmt(team.max_call)+' pts':'—'} &nbsp;·&nbsp;
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
    <div class="oc-squad-name">${esc(p.name)}</div>
    <div class="oc-squad-chips">
      ${p.role?`<span class="oc-squad-role">${esc(p.role)}</span>`:''}
      ${p.tier_name?`<span class="oc-squad-tier" style="border-color:${esc(p.tier_color)};color:${esc(p.tier_color)}">${esc(p.tier_name)}</span>`:''}
    </div>
  </div>
  <div class="oc-squad-pts">${fmt(p.points)} pts</div>
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
    const input = $('ocBidInput');
    if (input && !input.disabled) input.value = amount;
};

// ── Bid confirm ────────────────────────────────────────────────────────
window.ocOpenBidConfirm = function() {
    const { myTeam, player } = S;
    if (!myTeam || !player) return;
    const input = $('ocBidInput');
    const amount = parseInt((input&&input.value)||'0', 10);
    if (!amount || amount < (myTeam.effective_base||1)) {
        toast('Bid must be at least '+fmt(myTeam.effective_base)+' pts', 'err'); return;
    }
    if (myTeam.max_call>0 && amount>myTeam.max_call) {
        toast('Exceeds your max call of '+fmt(myTeam.max_call)+' pts', 'err'); return;
    }
    S.pendingBid = { playerId: player.id, teamId: myTeam.id, amount };
    txt('ocConfirmPlayer', player.name);
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
            toast('Bid of '+fmt(bid.amount)+' pts placed! 🎯','ok');
            ocCancelBidConfirm();
            fetchData();
        } else {
            toast(res.error||'Bid failed','err');
        }
    })
    .catch(()=>toast('Network error. Please retry.','err'))
    .finally(()=>{ if(btn) btn.disabled=false; });
};

// ── Poll ───────────────────────────────────────────────────────────────
function fetchData() {
    fetch('/auction/owner/data', {cache:'no-store'})
    .then(r => r.ok ? r.json() : Promise.reject(r.status))
    .then(data => {
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

        S.player  = incoming;
        S.myTeam  = data.my_team || null;
        S.teams   = data.teams || [];
        // Server sends slabs sorted descending by from_amount
        S.slabs   = data.slabs || [];
        S.presets = data.presets || [];

        renderPlayer(S.player);
        renderBidPanel(S.myTeam, S.player);
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

// ── Boot ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    fetchData();
    S.pollTimer = setInterval(fetchData, 3000);
    // Expose fetch globally so external scripts (e.g. debug tools) can trigger a refresh,
    // matching the window._auctionLbPoll pattern used on /auction/live-board.
    window._auctionOcFetch = fetchData;
});

})();
