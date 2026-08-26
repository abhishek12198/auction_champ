/* Live bid pad on display_auction — survives Next / Sell / Unsold player swaps */
(function () {
    'use strict';
    if (window.__acLiveBidBooted) {
        if (typeof window.acInitLiveBidPad === 'function') window.acInitLiveBidPad();
        return;
    }
    window.__acLiveBidBooted = true;

    var DATA_URL = '/auction/auctioneer/data';
    var BID_URL = '/auction/auctioneer/place-bid';
    var STORE_CLOSED = 'acLiveBidClosed';
    var STORE_EXPANDED = 'acLiveBidExpanded';
    var lastHtml = '';
    var busyId = 0;
    var allowed = false;
    var teamsCache = [];
    var playerCache = null;
    var selectedTeam = null;
    var pollTimer = null;
    var boundPad = null;

    function padEl() { return document.getElementById('acLiveBidPad'); }
    function launchEl() { return document.getElementById('acLiveBidLaunch'); }
    function gridEl() { return document.getElementById('acLiveBidGrid'); }
    function metaEl() { return document.getElementById('acLiveBidMeta'); }
    function toastEl() { return document.getElementById('acLiveBidToast'); }
    function modalEl() { return document.getElementById('acLiveBidModal'); }
    function infoEl() { return document.getElementById('acLiveBidInfo'); }

    function tournamentId() {
        var pad = padEl();
        return (pad && pad.getAttribute('data-tournament-id')) || '';
    }
    function dataUrl() {
        var id = tournamentId();
        return DATA_URL + (id ? ('?tournament_id=' + encodeURIComponent(id)) : '');
    }
    function remaining(team) {
        return team.remaining_points != null ? team.remaining_points : team.remaining_points;
    }
    function totalPts(team) {
        return team.total_points != null ? team.total_points : team.total_points;
    }
    function maxCall(team) {
        return team.max_call != null ? team.max_call : team.max_call;
    }
    function canBid(team) {
        return !!(team.can_bid || team.can_bid);
    }
    function bidReason(team) {
        return team.can_bid_reason || team.can_bid_reason || '';
    }
    function logoUrl(team) {
        return team.logo_url || team.logo_url || '';
    }
    function fmt(n) {
        if (n === null || n === undefined) return '—';
        if (window.fmtUnit) return window.fmtUnit(n);
        return Number(n).toLocaleString();
    }
    function esc(s) {
        return String(s || '').replace(/[&<>"']/g, function (c) {
            return ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c];
        });
    }
    function toast(msg, err) {
        var el = toastEl();
        if (!el) return;
        el.textContent = msg;
        el.className = 'ac-livebid-toast is-on' + (err ? ' is-err' : '');
        clearTimeout(el._t);
        el._t = setTimeout(function () { el.className = 'ac-livebid-toast'; }, 2800);
    }
    function csrfToken() {
        var pad = padEl();
        var csrf = pad && pad.getAttribute('data-csrf');
        if (csrf) return csrf;
        var m = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
        return m ? decodeURIComponent(m[1]) : '';
    }
    function isClosed() {
        try { return sessionStorage.getItem(STORE_CLOSED) === '1'; } catch (e) { return false; }
    }
    function isExpanded() {
        try {
            var v = sessionStorage.getItem(STORE_EXPANDED);
            if (v === null) return true;
            return v === '1';
        } catch (e) { return true; }
    }
    function setClosed(v) {
        try { sessionStorage.setItem(STORE_CLOSED, v ? '1' : '0'); } catch (e) { /* ignore */ }
    }
    function setExpanded(v) {
        try { sessionStorage.setItem(STORE_EXPANDED, v ? '1' : '0'); } catch (e) { /* ignore */ }
    }
    function applyChrome() {
        var pad = padEl();
        var launch = launchEl();
        var toggleBtn = document.getElementById('acLiveBidToggle');
        if (!pad) return;
        if (document.body) document.body.classList.add('ac-showcase');
        pad.classList.toggle('is-on', allowed);
        var closed = !allowed || isClosed();
        var expanded = allowed && !closed && isExpanded();
        pad.classList.toggle('is-open', allowed && !closed);
        pad.classList.toggle('is-expanded', expanded);
        if (launch) launch.classList.toggle('is-on', allowed && closed);
        if (toggleBtn) {
            toggleBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
            toggleBtn.textContent = expanded ? 'Show less' : 'View all teams';
        }
    }
    function jsonRpc(url, params, cb) {
        var xhr = new XMLHttpRequest();
        xhr.open('POST', url, true);
        xhr.withCredentials = true;
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.setRequestHeader('X-CSRFToken', csrfToken());
        xhr.onload = function () {
            try {
                var res = JSON.parse(xhr.responseText);
                cb(null, res.result);
            } catch (e) { cb(e, null); }
        };
        xhr.onerror = function () { cb(new Error('network'), null); };
        xhr.send(JSON.stringify({ jsonrpc: '2.0', method: 'call', id: Date.now(), params: params || {} }));
    }
    function getJson(url, cb) {
        var xhr = new XMLHttpRequest();
        xhr.open('GET', url, true);
        xhr.withCredentials = true;
        xhr.onload = function () {
            if (xhr.status === 401 || xhr.status === 403) {
                cb('denied', null);
                return;
            }
            try { cb(null, JSON.parse(xhr.responseText)); }
            catch (e) { cb(e, null); }
        };
        xhr.onerror = function () { cb(new Error('network'), null); };
        xhr.send();
    }
    function slabsOf(team) {
        if (!team) return [];
        return team['slabs'] || team.slabs || [];
    }
    function slabFrom(s) {
        if (s.from_amount != null) return s.from_amount;
        if (s.from_amount != null) return s.from_amount;
        return 0;
    }
    function slabIncAmt(s) {
        if (s.increment != null) return s.increment;
        if (s.increment != null) return s.increment;
        return 1;
    }
    function slabInc(amount, slabs) {
        for (var i = 0; i < slabs.length; i++) {
            var from = slabFrom(slabs[i]);
            var inc = slabIncAmt(slabs[i]);
            if (amount >= from) return inc || 1;
        }
        return 1;
    }
    function presetBids(team) {
        var start = Number(team.next_bid || team.effective_base || 0);
        var max = maxCall(team) || 0;
        var sl = slabsOf(team);
        var out = [];
        var v = start;
        for (var i = 0; i < 6; i++) {
            if (max && v > max) break;
            if (v > 0 && out.indexOf(v) === -1) out.push(v);
            v = v + (slabInc(v, sl) || 1);
        }
        return out;
    }
    function snapDown(amount, slabs) {
        for (var i = 0; i < slabs.length; i++) {
            var from = slabs[i].from_amount != null ? slabs[i].from_amount : slabs[i].from_amount;
            var inc = slabs[i].increment != null ? slabs[i].increment : slabs[i].increment;
            if (amount >= from) {
                return from + Math.floor((amount - from) / (inc || 1)) * (inc || 1);
            }
        }
        return amount;
    }
    function leadTeam(player) {
        if (!player || !player.current_bid) return null;
        return player.current_bid_team || player.current_bid_team || null;
    }
    function squadSlotsLeft(team) {
        if (team.remaining_players != null) return Number(team.remaining_players);
        if (team.remaining_players != null) return Number(team.remaining_players);
        return null;
    }
    function isSquadFull(team) {
        var left = squadSlotsLeft(team);
        if (left != null && left <= 0) return true;
        var reason = (bidReason(team) || '').toLowerCase();
        return reason.indexOf('squad full') !== -1;
    }

    function render(data) {
        var pad = padEl();
        var grid = gridEl();
        var meta = metaEl();
        if (!pad || !grid) return;
        var player = data.current_player || null;
        var teams = (data.teams || []).filter(function (t) { return !isSquadFull(t); });
        teamsCache = teams;
        playerCache = player;
        if (!teams.length) {
            allowed = false;
            applyChrome();
            return;
        }
        allowed = true;
        applyChrome();
        var lead = leadTeam(player);
        var leadHead = document.getElementById('acLiveBidLeadHead');
        var leadLogo = document.getElementById('acLiveBidLeadLogo');
        var leadName = document.getElementById('acLiveBidLeadName');
        var leadPts = document.getElementById('acLiveBidLeadPts');
        var leadLogoSrc = lead ? logoUrl(lead) : '';
        var leadAmt = player && player.current_bid ? Number(player.current_bid) : 0;
        if (leadHead) {
            if (lead && (lead.name || leadLogoSrc || leadAmt)) {
                leadHead.classList.add('is-on');
                if (leadName) leadName.textContent = lead.name || '';
                if (leadLogo) {
                    if (leadLogoSrc) {
                        leadLogo.src = leadLogoSrc;
                        leadLogo.style.display = '';
                    } else {
                        leadLogo.removeAttribute('src');
                        leadLogo.style.display = 'none';
                    }
                }
                if (leadPts) {
                    if (leadAmt) {
                        leadPts.textContent = fmt(leadAmt);
                        leadPts.style.display = '';
                    } else {
                        leadPts.textContent = '';
                        leadPts.style.display = 'none';
                    }
                }
            } else {
                leadHead.classList.remove('is-on');
                if (leadName) leadName.textContent = '';
                if (leadPts) {
                    leadPts.textContent = '';
                    leadPts.style.display = 'none';
                }
            }
        }
        var html = teams.map(function (team) {
            var leadOn = !!(lead && Number(lead.id) === Number(team.id));
            var off = !player || !canBid(team);
            var rem = remaining(team) || 0;
            var tot = totalPts(team) || 0;
            var pct = tot > 0 ? Math.max(0, Math.min(100, (rem / tot) * 100)) : 0;
            var barMod = pct > 50 ? '' : pct > 25 ? ' is-mid' : ' is-low';
            var cls = 'ac-livebid-tile'
                + (off ? ' is-off' : '')
                + (leadOn ? ' is-lead' : '')
                + (busyId === team.id ? ' is-busy' : '');
            var logo = logoUrl(team)
                ? '<img class="ac-livebid-logo" src="' + esc(logoUrl(team)) + '" alt=""/>'
                : '<span class="ac-livebid-ph">' + esc((team.name || '?').charAt(0)) + '</span>';
            var left = squadSlotsLeft(team);
            var squadMax = team.max_players != null ? Number(team.max_players) : 0;
            var recruited = (left != null && squadMax) ? Math.max(0, squadMax - left) : null;
            var squadTxt = (recruited != null && squadMax)
                ? (recruited + '/' + squadMax)
                : (squadMax ? ('—/' + squadMax) : '');
            var maxBid = maxCall(team);
            var foot;
            if (off && !leadOn) {
                foot = '<div class="ac-livebid-off" title="' + esc(bidReason(team)) + '">' + esc(bidReason(team) || 'Off') + '</div>';
            } else if (!leadOn) {
                foot = '<span class="ac-livebid-chip" data-custom="' + team.id + '" title="Enter custom points">' + fmt(team.next_bid) + '</span>';
            } else {
                foot = '<div class="ac-livebid-leadamt">' + fmt(player.current_bid) + '</div>';
            }
            return '<button type="button" class="' + cls + '" data-team-id="' + team.id + '"'
                + ' title="' + esc(team.name) + '">'
                + '<div class="ac-livebid-head">'
                + logo
                + '<span class="ac-livebid-name">' + esc(team.name) + '</span>'
                + foot
                + '</div>'
                + '<div class="ac-livebid-purse-bar"><div class="ac-livebid-purse-fill' + barMod + '" style="width:' + pct.toFixed(1) + '%"></div></div>'
                + '<div class="ac-livebid-meta">'
                + '<span class="ac-livebid-purse" title="Purse">' + fmt(rem) + '</span>'
                + (squadTxt ? '<span class="ac-livebid-squad" title="Squad">' + esc(squadTxt) + '</span>' : '')
                + '<span class="ac-livebid-max" title="Max bid">Max ' + fmt(maxBid) + '</span>'
                + '</div>'
                + '</button>';
        }).join('');
        if (html !== lastHtml) {
            grid.innerHTML = html;
            lastHtml = html;
        }
    }

    function poll() {
        if (!padEl()) return;
        getJson(dataUrl(), function (err, data) {
            if (err || !data || data.error === 'not_auctioneer') {
                allowed = false;
                applyChrome();
                return;
            }
            render(data);
        });
    }

    function placeBid(team, amount, done) {
        var player = playerCache;
        if (!player || !team) { done('No player on stage'); return; }
        jsonRpc(BID_URL, {
            player_id: player.id,
            team_id: team.id,
            bid_amount: amount,
        }, function (rpcErr, result) {
            if (rpcErr || !result) { done('Network error'); return; }
            if (!result.success) { done(result.error || 'Bid failed'); return; }
            done(null, result);
        });
    }

    function validateCustom(team, value) {
        var hint = document.getElementById('acLbHint');
        var btn = document.getElementById('acLbPlace');
        if (!hint || !btn) return;
        var base = team.effective_base || 0;
        var max = maxCall(team) || 0;
        if (value < base) {
            hint.textContent = 'Below base (' + fmt(base) + ')';
            btn.disabled = true;
        } else if (max && value > max) {
            hint.textContent = 'Exceeds max call (' + fmt(max) + ')';
            btn.disabled = true;
        } else {
            hint.textContent = '';
            btn.disabled = false;
        }
    }

    function openCustom(teamId) {
        var modal = modalEl();
        var team = teamsCache.filter(function (t) { return t.id === teamId; })[0];
        var player = playerCache;
        if (!modal || !team || !player || !canBid(team)) return;
        selectedTeam = team;
        var logo = document.getElementById('acLbModalLogo');
        if (logo) {
            logo.src = logoUrl(team);
            logo.style.display = logoUrl(team) ? '' : 'none';
        }
        var teamEl = document.getElementById('acLbModalTeam');
        var meta = document.getElementById('acLbModalMeta');
        var baseEl = document.getElementById('acLbModalBase');
        var maxEl = document.getElementById('acLbModalMax');
        var input = document.getElementById('acLbBidInput');
        if (teamEl) teamEl.textContent = team.name || '';
        if (meta) meta.textContent = 'Remaining ' + fmt(remaining(team)) + ' · Max ' + fmt(maxCall(team));
        if (baseEl) baseEl.textContent = fmt(team.effective_base);
        if (maxEl) maxEl.textContent = fmt(maxCall(team));
        if (input) input.value = team.next_bid || '';
        validateCustom(team, team.next_bid || 0);
        var presets = document.getElementById('acLbPresets');
        if (presets) {
            var vals = presetBids(team);
            var cur = Number(team.next_bid || 0);
            presets.innerHTML = vals.map(function (v) {
                return '<button type="button" class="ac-livebid-preset' + (v === cur ? ' is-on' : '') + '" data-preset="' + v + '">' + fmt(v) + '</button>';
            }).join('');
        }
        modal.hidden = false;
        modal.classList.add('is-on');
    }
    function closeCustom() {
        selectedTeam = null;
        var modal = modalEl();
        if (!modal) return;
        modal.classList.remove('is-on');
        modal.hidden = true;
    }

    function squadRecruited(team) {
        var left = squadSlotsLeft(team);
        var maxP = Number(team.max_players || 0) || 0;
        if (!maxP) return '—';
        if (left == null || isNaN(left)) return '— / ' + maxP;
        return Math.max(0, maxP - left) + ' / ' + maxP;
    }

    function closeTeamInfo() {
        var el = infoEl();
        if (!el) return;
        el.classList.remove('is-on');
        el.hidden = true;
    }

    function openTeamInfo(teamId) {
        var team = teamsCache.filter(function (t) { return Number(t.id) === Number(teamId); })[0];
        var el = infoEl();
        if (!el || !team) return;
        closeCustom();
        var logo = document.getElementById('acLbInfoLogo');
        var nameEl = document.getElementById('acLbInfoName');
        var mgrEl = document.getElementById('acLbInfoMgr');
        var leadEl = document.getElementById('acLbInfoLead');
        var rows = document.getElementById('acLbInfoRows');
        var note = document.getElementById('acLbInfoNote');
        var src = logoUrl(team);
        if (logo) {
            if (src) {
                logo.src = src;
                logo.style.display = '';
            } else {
                logo.removeAttribute('src');
                logo.style.display = 'none';
            }
        }
        if (nameEl) nameEl.textContent = team.name || '';
        if (mgrEl) {
            mgrEl.textContent = team.manager || '';
            mgrEl.style.display = team.manager ? '' : 'none';
        }
        var lead = leadTeam(playerCache);
        var isLead = !!(lead && Number(lead.id) === Number(team.id));
        if (leadEl) leadEl.hidden = !isLead;
        var rem = remaining(team) || 0;
        var tot = totalPts(team) || 0;
        var nextBid = team.next_bid || team.effective_base || 0;
        var rowsHtml = [
            ['Purse left / max purse', fmt(rem) + ' / ' + fmt(tot)],
            ['Squad / full squad', squadRecruited(team)],
            ['Next bid', fmt(nextBid)],
            ['Next max point', fmt(maxCall(team))],
            ['Base', fmt(team.effective_base)],
        ].map(function (row) {
            return '<div class="ac-livebid-info-row"><span>' + esc(row[0]) + '</span><strong>' + esc(row[1]) + '</strong></div>';
        }).join('');
        if (rows) rows.innerHTML = rowsHtml;
        if (note) {
            if (!canBid(team) && bidReason(team)) {
                note.textContent = bidReason(team);
                note.style.display = '';
            } else {
                note.textContent = '';
            }
        }
        el.hidden = false;
        el.classList.add('is-on');
    }

    var holdTimer = null;
    var holdFired = false;
    var holdStartX = 0;
    var holdStartY = 0;

    function liveBidTileFrom(ev) {
        return ev.target && ev.target.closest && ev.target.closest('#acLiveBidGrid .ac-livebid-tile');
    }
    function clearHoldTimer() {
        if (holdTimer) { clearTimeout(holdTimer); holdTimer = null; }
    }
    function startHold(teamId) {
        clearHoldTimer();
        holdTimer = setTimeout(function () {
            holdTimer = null;
            holdFired = true;
            openTeamInfo(teamId);
            setTimeout(function () { holdFired = false; }, 700);
        }, 480);
    }

    function refreshPad() {
        var pad = padEl();
        if (!pad) return;
        if (boundPad !== pad) {
            boundPad = pad;
            lastHtml = '';
        }
        applyChrome();
        poll();
    }
    window.acInitLiveBidPad = refreshPad;

    document.addEventListener('pointerdown', function (ev) {
        var tile = liveBidTileFrom(ev);
        if (!tile) return;
        if (ev.pointerType === 'mouse' && ev.button !== 0) return;
        holdStartX = ev.clientX;
        holdStartY = ev.clientY;
        startHold(parseInt(tile.getAttribute('data-team-id'), 10));
    });
    document.addEventListener('pointermove', function (ev) {
        if (!holdTimer) return;
        if (Math.abs(ev.clientX - holdStartX) > 12 || Math.abs(ev.clientY - holdStartY) > 12) {
            clearHoldTimer();
        }
    });
    document.addEventListener('pointerup', clearHoldTimer);
    document.addEventListener('pointercancel', clearHoldTimer);
    document.addEventListener('contextmenu', function (ev) {
        var tile = liveBidTileFrom(ev);
        if (!tile) return;
        ev.preventDefault();
        holdFired = true;
        openTeamInfo(parseInt(tile.getAttribute('data-team-id'), 10));
        setTimeout(function () { holdFired = false; }, 700);
    });

    document.addEventListener('click', function (ev) {
        if (ev.target.closest('#acLbInfoClose') || ev.target.id === 'acLiveBidInfo') {
            closeTeamInfo();
            holdFired = false;
            return;
        }
        if (holdFired) {
            holdFired = false;
            ev.preventDefault();
            ev.stopPropagation();
            return;
        }
        if (ev.target.closest('#acLiveBidToggle')) {
            setExpanded(!isExpanded());
            applyChrome();
            return;
        }
        if (ev.target.closest('#acLiveBidClose')) {
            setClosed(true);
            setExpanded(false);
            applyChrome();
            return;
        }
        if (ev.target.closest('#acLiveBidLaunch')) {
            setClosed(false);
            setExpanded(true);
            applyChrome();
            return;
        }
        if (ev.target.closest('#acLbModalClose')) {
            closeCustom();
            return;
        }
        var presetBtn = ev.target.closest('#acLbPresets [data-preset]');
        if (presetBtn && selectedTeam) {
            var pv = parseInt(presetBtn.getAttribute('data-preset'), 10) || 0;
            var pin = document.getElementById('acLbBidInput');
            if (pin) pin.value = pv;
            validateCustom(selectedTeam, pv);
            var wrap = document.getElementById('acLbPresets');
            if (wrap) {
                var btns = wrap.querySelectorAll('.ac-livebid-preset');
                for (var b = 0; b < btns.length; b++) {
                    btns[b].classList.toggle('is-on', btns[b] === presetBtn);
                }
            }
            return;
        }
        var modal = modalEl();
        if (modal && ev.target === modal) {
            closeCustom();
            return;
        }
        if (ev.target.closest('#acLbDec')) {
            if (!selectedTeam) return;
            var input = document.getElementById('acLbBidInput');
            if (!input) return;
            var cur = parseInt(input.value, 10) || 0;
            var sl = slabsOf(selectedTeam);
            var base = selectedTeam.effective_base || 1;
            var step = slabInc(cur, sl);
            cur = Math.max(base, snapDown(Math.max(0, cur - step), sl));
            input.value = cur;
            validateCustom(selectedTeam, cur);
            return;
        }
        if (ev.target.closest('#acLbInc')) {
            if (!selectedTeam) return;
            var incInput = document.getElementById('acLbBidInput');
            if (!incInput) return;
            var next = parseInt(incInput.value, 10) || 0;
            var live = playerCache ? (playerCache.current_bid || 0) : 0;
            if (next <= live) next = selectedTeam.next_bid;
            else next = next + slabInc(next, slabsOf(selectedTeam));
            incInput.value = next;
            validateCustom(selectedTeam, next);
            return;
        }
        if (ev.target.closest('#acLbPlace')) {
            if (!selectedTeam) return;
            var amount = parseInt((document.getElementById('acLbBidInput') || {}).value, 10);
            var btn = document.getElementById('acLbPlace');
            if (btn) btn.disabled = true;
            placeBid(selectedTeam, amount, function (err, result) {
                if (btn) btn.disabled = false;
                if (err || !result) { toast(err || 'Bid failed', true); return; }
                toast(fmt(result.current_bid) + ' — ' + (result.team_name || ''));
                closeCustom();
                poll();
            });
            return;
        }
        var chip = ev.target.closest('#acLiveBidGrid [data-custom]');
        if (chip) {
            ev.preventDefault();
            ev.stopPropagation();
            openCustom(parseInt(chip.getAttribute('data-custom'), 10));
            return;
        }
        var tile = ev.target.closest('#acLiveBidGrid .ac-livebid-tile');
        if (!tile || tile.disabled || tile.classList.contains('is-off')) return;
        var teamId = parseInt(tile.getAttribute('data-team-id'), 10);
        var team = teamsCache.filter(function (t) { return t.id === teamId; })[0];
        if (!team || !canBid(team)) return;
        busyId = teamId;
        var grid = gridEl();
        if (grid) {
            var tiles = grid.querySelectorAll('.ac-livebid-tile.is-lead');
            for (var i = 0; i < tiles.length; i++) tiles[i].classList.remove('is-lead');
        }
        tile.classList.add('is-busy', 'is-lead');
        placeBid(team, team.next_bid, function (err, result) {
            busyId = 0;
            if (err || !result) { toast(err || 'Bid failed', true); poll(); return; }
            toast(fmt(result.current_bid) + ' — ' + (result.team_name || ''));
            poll();
        });
    });
    document.addEventListener('input', function (ev) {
        if (ev.target && ev.target.id === 'acLbBidInput' && selectedTeam) {
            validateCustom(selectedTeam, parseInt(ev.target.value, 10) || 0);
        }
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeCustom();
            closeTeamInfo();
        }
    });

    var obsTimer = null;
    var observer = new MutationObserver(function () {
        if (!padEl()) return;
        if (boundPad === padEl()) return;
        clearTimeout(obsTimer);
        obsTimer = setTimeout(refreshPad, 30);
    });
    function watchZone() {
        var zone = document.querySelector('[data-player-zone]') || document.body;
        observer.observe(zone, { childList: true, subtree: true });
    }

    function wrapChangeImage() {
        if (typeof window.changeImage !== 'function' || window.changeImage._acLiveBid) return;
        var orig = window.changeImage;
        window.changeImage = function () {
            var ret = orig.apply(this, arguments);
            Promise.resolve(ret).then(function () { setTimeout(refreshPad, 50); });
            return ret;
        };
        window.changeImage._acLiveBid = true;
    }

    function projectorSseUrl() {
        var path = location.pathname || '';
        var m = path.match(/^\/([^/]+)\/auction\/display_auction\/([^/]+)/);
        if (!m) return '';
        return '/' + m[1] + '/auction/projector/' + m[2] + '/events';
    }
    function startHttpPoll() {
        if (!pollTimer) {
            pollTimer = setInterval(function () {
                wrapChangeImage();
                poll();
            }, 2500);
        }
    }
    function stopHttpPoll() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }
    function startBidSse() {
        var url = projectorSseUrl();
        if (!url || typeof EventSource === 'undefined') {
            startHttpPoll();
            return;
        }
        var es;
        try {
            es = new EventSource(url);
        } catch (e) {
            startHttpPoll();
            return;
        }
        function onEvt() {
            stopHttpPoll();
            wrapChangeImage();
            poll();
        }
        es.addEventListener('snapshot', onEvt);
        es.addEventListener('auction.update', onEvt);
        es.onopen = function () {
            stopHttpPoll();
            poll();
        };
        es.onerror = function () {
            startHttpPoll();
        };
    }

    refreshPad();
    watchZone();
    wrapChangeImage();
    startBidSse();
})();
