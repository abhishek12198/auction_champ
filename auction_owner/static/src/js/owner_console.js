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
    // Track last known bid to detect rival changes between polls
    _lastBid: { playerId: null, bid: 0, teamId: null },
    _counterTs: null,   // last-seen counter_started_at; null = not yet initialised
    _counterInit: false,
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
    // Populate team logo + name
    const logoEl = $('ocSoldLogo');
    const nameEl = $('ocSoldTeamName');
    if (soldData) {
        const logoUrl = soldData.logo_url || '';
        const teamName = soldData.team || soldData.name || '';
        if (logoEl) {
            if (logoUrl) { logoEl.src = logoUrl; logoEl.style.display = 'block'; }
            else         { logoEl.src = '';       logoEl.style.display = 'none'; }
        }
        if (nameEl) nameEl.textContent = teamName;
    } else {
        if (logoEl) { logoEl.src = ''; logoEl.style.display = 'none'; }
        if (nameEl) nameEl.textContent = '';
    }
    // restart stamp animation
    overlay.classList.remove('oc-sold-show');
    void overlay.offsetWidth;
    overlay.classList.add('oc-sold-show');
    hideUnsoldOverlay();
}

function hideSoldOverlay() {
    const overlay = $('ocSoldOverlay');
    if (overlay) overlay.classList.remove('oc-sold-show');
}

// ── UNSOLD overlay ─────────────────────────────────────────────
function showUnsoldOverlay() {
    const overlay = $('ocUnsoldOverlay');
    if (!overlay) return;
    overlay.classList.remove('oc-unsold-show');
    void overlay.offsetWidth;
    overlay.classList.add('oc-unsold-show');
    hideSoldOverlay();
}

function hideUnsoldOverlay() {
    const overlay = $('ocUnsoldOverlay');
    if (overlay) overlay.classList.remove('oc-unsold-show');
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

    // Show SOLD/UNSOLD overlay based on player state; hide for all other states
    if (p.state === 'sold') {
        showSoldOverlay(p.current_bid_team || null);
    } else if (p.state === 'unsold') {
        showUnsoldOverlay();
    } else {
        hideSoldOverlay();
        hideUnsoldOverlay();
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
    const canRevoke = rv.can_revoke && rv.remaining > 0;
    if (btn) btn.disabled = !canRevoke;
    if (hint) {
        if (rv.remaining <= 0) {
            hint.textContent = 'No revokes left';
        } else {
            hint.textContent = rv.remaining + '/' + rv.max + ' left';
        }
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

// ── Revoke last bid ────────────────────────────────────────────────────
window.ocRevokeBid = function() {
    const { myTeam, player, revoke } = S;
    if (!myTeam || !player) return;
    if (!revoke || !revoke.can_revoke || revoke.remaining <= 0) {
        toast('Revoke not available', 'err'); return;
    }
    const remaining = revoke.remaining;
    if (!confirm(
        'Revoke your bid of ' + fmt(player.current_bid) + ' pts?\n' +
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
                ? 'Bid revoked ✓ — ' + res.prev_team_name + ' leads with ' + fmt(res.new_bid) + ' pts'
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
        S.revoke  = data.revoke  || null;

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
  <div style="font-size:.86rem;font-weight:700;color:#e8edf8;line-height:1.25;">${esc(p.name)}</div>
  <div style="display:flex;gap:5px;flex-wrap:wrap;justify-content:center;">
    ${p.role      ? `<span style="${chipStyle(acl, 'rgba(255,255,255,.08)')}">${esc(p.role)}</span>`       : ''}
    ${p.tier_name ? `<span style="${chipStyle(p.tier_color || acl, 'transparent')}border:1px solid ${esc(p.tier_color || ac)};">${esc(p.tier_name)}</span>` : ''}
  </div>
  <div style="font-size:.95rem;font-weight:800;color:${acl};">${fmtN(p.points)} pts</div>
</div>`
        : p => `
<div style="background:#111520;border:1px solid rgba(255,255,255,.07);border-radius:10px;padding:10px 13px;display:flex;align-items:center;gap:12px;">
  ${imgEl(p.photo_url, 44, `border-radius:50%;border:2px solid ${ac};flex-shrink:0;`)}
  <div style="flex:1;min-width:0;">
    <div style="font-size:.86rem;font-weight:700;color:#e8edf8;">${esc(p.name)}</div>
    <div style="display:flex;gap:5px;margin-top:4px;flex-wrap:wrap;">
      ${p.role      ? `<span style="${chipStyle(acl, 'rgba(255,255,255,.08)')}">${esc(p.role)}</span>`       : ''}
      ${p.tier_name ? `<span style="${chipStyle(p.tier_color || acl, 'transparent')}border:1px solid ${esc(p.tier_color || ac)};">${esc(p.tier_name)}</span>` : ''}
    </div>
  </div>
  <div style="font-size:.86rem;font-weight:800;color:${acl};flex-shrink:0;">${fmtN(p.points)} pts</div>
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
      <div style="font-size:.74rem;color:#8899bb;margin-top:4px;">${fmtN(myTeam.remaining_points)} / ${fmtN(myTeam.total_points)} pts remaining</div>
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
document.addEventListener('DOMContentLoaded', () => {
    fetchData();
    S.pollTimer = setInterval(fetchData, 3000);
    // Expose fetch globally so external scripts (e.g. debug tools) can trigger a refresh,
    // matching the window._auctionLbPoll pattern used on /auction/live-board.
    window._auctionOcFetch = fetchData;
});

})();
