/* global */ (function () {
    'use strict';

    /* ── Navbar scroll effect ── */
    var nav = document.getElementById('acNav');
    if (nav) {
        function onScroll() {
            if (window.scrollY > 60) { nav.classList.add('scrolled'); }
            else { nav.classList.remove('scrolled'); }
        }
        window.addEventListener('scroll', onScroll, { passive: true });
        onScroll();
    }

    /* ── Mobile menu toggle ── */
    var toggle  = document.getElementById('acMenuToggle');
    var mobileNav = document.getElementById('acMobileNav');
    if (toggle && mobileNav) {
        toggle.addEventListener('click', function () {
            var open = mobileNav.classList.toggle('open');
            var icon = toggle.querySelector('i');
            if (icon) {
                icon.classList.toggle('fa-bars',   !open);
                icon.classList.toggle('fa-times',  open);
            }
        });
        document.addEventListener('click', function (e) {
            if (nav && !nav.contains(e.target)) {
                mobileNav.classList.remove('open');
                var icon = toggle.querySelector('i');
                if (icon) { icon.classList.add('fa-bars'); icon.classList.remove('fa-times'); }
            }
        });
        mobileNav.querySelectorAll('a').forEach(function (a) {
            a.addEventListener('click', function () {
                mobileNav.classList.remove('open');
                var icon = toggle.querySelector('i');
                if (icon) { icon.classList.add('fa-bars'); icon.classList.remove('fa-times'); }
            });
        });
    }

    /* ── FAQ accordion ── */
    document.querySelectorAll('.ac-faq-q').forEach(function (q) {
        q.addEventListener('click', function () {
            var item   = q.closest('.ac-faq-item');
            var wasOpen = item.classList.contains('open');
            document.querySelectorAll('.ac-faq-item').forEach(function (i) { i.classList.remove('open'); });
            if (!wasOpen) { item.classList.add('open'); }
        });
    });

    /* ── Smooth scroll for anchor links (offset for fixed nav) ── */
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
        a.addEventListener('click', function (e) {
            var href = a.getAttribute('href');
            if (!href || href === '#') return;
            var target = document.querySelector(href);
            if (!target) return;
            e.preventDefault();
            var navH = nav ? nav.getBoundingClientRect().height : 68;
            var top  = target.getBoundingClientRect().top + window.scrollY - navH - 12;
            window.scrollTo({ top: top, behavior: 'smooth' });
        });
    });

    /* ── Counter animation for hero stats ── */
    var statsAnimated = false;
    function animateStats() {
        if (statsAnimated) return;
        var strip = document.querySelector('.ac-hero-stats');
        if (!strip) return;
        if (strip.getBoundingClientRect().top < window.innerHeight + 60) {
            statsAnimated = true;
            document.querySelectorAll('.ac-stat-value[data-target]').forEach(function (el) {
                var raw    = el.getAttribute('data-target') || '';
                var suffix = raw.replace(/[\d,\.]+/, '');
                var numStr = raw.replace(/[^\d\.]/g, '');
                if (!numStr) { el.textContent = raw; return; }
                var target   = parseFloat(numStr);
                var isLarge  = target >= 1000;
                var duration = 1600;
                var start    = null;
                function step(ts) {
                    if (!start) start = ts;
                    var p = Math.min((ts - start) / duration, 1);
                    var eased = 1 - Math.pow(1 - p, 3);
                    var val   = eased * target;
                    el.textContent = (isLarge ? Math.floor(val).toLocaleString('en-IN') : Math.floor(val)) + suffix;
                    if (p < 1) { requestAnimationFrame(step); }
                    else       { el.textContent = raw; }
                }
                requestAnimationFrame(step);
            });
        }
    }
    window.addEventListener('scroll', animateStats, { passive: true });
    animateStats();

    /* ── Live Tournaments auto-refresh ──────────────────────── */
    var liveGrid = document.getElementById('acLiveGrid');
    if (liveGrid) {

        function esc(s) {
            return String(s || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }

        function buildStageHtml(lt) {
            if (lt.is_break) {
                return '<div class="ac-live-break-screen">'
                    + '<i class="fas fa-coffee"></i>'
                    + '<span>Break Time</span>'
                    + '</div>';
            }
            var p = lt.current_player;
            if (!p) {
                return '<div class="ac-live-waiting">'
                    + '<i class="fas fa-gavel"></i>'
                    + '<span>Auction in progress</span>'
                    + '</div>';
            }

            var stateBadge = '';
            if (p.state === 'sold')        stateBadge = '<span class="ac-live-sold-badge">SOLD</span>';
            else if (p.state === 'unsold') stateBadge = '<span class="ac-live-unsold-badge">UNSOLD</span>';
            else if (p.state === 'auction') stateBadge = '<span class="ac-live-stage-badge">ON STAGE</span>';

            var tierHtml = p.tier_name
                ? '<span class="ac-live-tier" style="background:' + esc(p.tier_color) + '22;color:' + esc(p.tier_color) + ';border-color:' + esc(p.tier_color) + '55;">' + esc(p.tier_name) + '</span>'
                : '';

            var extraHtml = '';
            if (p.state === 'sold' && p.sold_team_name) {
                extraHtml = '<div class="ac-live-sold-info">'
                    + '<span class="ac-live-sold-to">\u2192 ' + esc(p.sold_team_name) + '</span>'
                    + '<span class="ac-live-sold-pts">' + esc(String(p.sold_points || 0)) + ' pts</span>'
                    + '</div>';
            } else if (p.state === 'auction' && p.base_price) {
                extraHtml = '<div class="ac-live-base">'
                    + '<span class="ac-live-base-label">Base:</span>'
                    + '<span class="ac-live-base-val">' + esc(String(p.base_price)) + ' pts</span>'
                    + '</div>';
            }

            return '<div class="ac-live-player"><div class="ac-live-player-details">'
                + '<div class="ac-live-player-top-row">'
                + '<span class="ac-live-player-sl">#' + esc(String(p.sl_no || '')) + '</span>'
                + stateBadge
                + '</div>'
                + '<div class="ac-live-player-name">' + esc(p.name) + '</div>'
                + '<div class="ac-live-player-role">' + esc(p.role || '') + '</div>'
                + tierHtml + extraHtml
                + '</div></div>';
        }

        function refreshLiveTournaments() {
            fetch('/auction/live-tournaments/data', { cache: 'no-store' })
                .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
                .then(function (data) {
                    liveGrid.querySelectorAll('.ac-live-card').forEach(function (card) {
                        var tid = parseInt(card.getAttribute('data-tournament-id'), 10);
                        var lt  = null;
                        for (var i = 0; i < data.length; i++) {
                            if (data[i].tournament_id === tid) { lt = data[i]; break; }
                        }
                        if (!lt) return;

                        card.classList.toggle('ac-live-break-mode', !!lt.is_break);

                        var stage = card.querySelector('.ac-live-stage');
                        if (stage) { stage.innerHTML = buildStageHtml(lt); }

                        var bidMsg = card.querySelector('.ac-live-bid-msg');
                        if (bidMsg && lt.current_bid && lt.current_bid.message) {
                            bidMsg.textContent = lt.current_bid.message;
                        }

                        var statVals = card.querySelectorAll('.ac-live-stat-val');
                        if (statVals.length >= 3) {
                            statVals[0].textContent = String(lt.teams_count || 0);
                            statVals[1].textContent = String(lt.players_sold || 0);
                            statVals[2].textContent = String(lt.players_in_auction || 0);
                        }
                    });
                })
                .catch(function () { /* silent on network error */ });
        }

        setInterval(refreshLiveTournaments, 8000);
    }

})();
