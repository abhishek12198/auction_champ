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

})();
