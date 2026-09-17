/* global */ (function () {
    'use strict';

    var cells = document.querySelectorAll('.ac-cal-cell');
    var panels = document.querySelectorAll('.ac-cal-day-panel');
    var districtBtn = document.getElementById('acCalDistrictBtn');
    var districtModal = document.getElementById('acCalDistrictModal');
    var districtSearch = document.getElementById('acCalDistrictSearch');
    var districtSubmit = document.getElementById('acCalDistrictSubmit');
    var districtOptions = districtModal
        ? districtModal.querySelectorAll('.ac-cal-district-option')
        : [];
    var pendingDistrict = districtBtn
        ? (districtBtn.getAttribute('data-district') || 'all')
        : 'all';

    function openDay(iso) {
        cells.forEach(function (cell) {
            cell.classList.toggle('is-selected', cell.getAttribute('data-day') === iso);
        });
        panels.forEach(function (panel) {
            var match = panel.getAttribute('data-day') === iso;
            panel.classList.toggle('is-open', match);
        });
        var open = document.querySelector('.ac-cal-day-panel.is-open');
        if (open && open.querySelector('.ac-cal-card')) {
            open.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }

    cells.forEach(function (cell) {
        cell.addEventListener('click', function () {
            openDay(cell.getAttribute('data-day'));
        });
    });

    function calendarUrl(district) {
        var url = new URL(window.location.href);
        if (district && district !== 'all') {
            url.searchParams.set('district', district);
        } else {
            url.searchParams.set('district', 'all');
        }
        url.searchParams.delete('geo');
        return url.toString();
    }

    function setDistrictOption(value) {
        pendingDistrict = String(value || 'all');
        districtOptions.forEach(function (opt) {
            var active = String(opt.getAttribute('data-district')) === pendingDistrict;
            opt.classList.toggle('is-active', active);
            opt.setAttribute('aria-selected', active ? 'true' : 'false');
        });
    }

    function openDistrictModal() {
        if (!districtModal) {
            return;
        }
        pendingDistrict = districtBtn
            ? (districtBtn.getAttribute('data-district') || 'all')
            : 'all';
        setDistrictOption(pendingDistrict);
        if (districtSearch) {
            districtSearch.value = '';
            filterDistrictOptions('');
        }
        districtModal.hidden = false;
        districtModal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('ac-cal-modal-open');
        if (districtSearch) {
            districtSearch.focus();
        }
    }

    function closeDistrictModal() {
        if (!districtModal) {
            return;
        }
        districtModal.hidden = true;
        districtModal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('ac-cal-modal-open');
        if (districtBtn) {
            districtBtn.focus();
        }
    }

    function filterDistrictOptions(query) {
        var needle = (query || '').trim().toLowerCase();
        districtOptions.forEach(function (opt) {
            var name = (opt.getAttribute('data-name') || opt.textContent || '').toLowerCase();
            var show = !needle || name.indexOf(needle) !== -1 || opt.getAttribute('data-district') === 'all';
            if (opt.getAttribute('data-district') === 'all' && needle && name.indexOf(needle) === -1) {
                show = 'all districts'.indexOf(needle) !== -1;
            }
            opt.hidden = !show;
        });
    }

    function applyManualDistrict(district) {
        try { sessionStorage.setItem('ac_cal_district_manual', '1'); } catch (e) {}
        window.location.href = calendarUrl(district);
    }

    if (districtBtn && districtModal) {
        districtBtn.addEventListener('click', function (ev) {
            ev.preventDefault();
            openDistrictModal();
        });
        districtBtn.addEventListener('dblclick', function (ev) {
            ev.preventDefault();
            openDistrictModal();
        });
        districtModal.addEventListener('click', function (ev) {
            if (ev.target && ev.target.getAttribute('data-ac-cal-modal-close')) {
                closeDistrictModal();
            }
        });
        districtOptions.forEach(function (opt) {
            opt.addEventListener('click', function () {
                setDistrictOption(opt.getAttribute('data-district'));
            });
            opt.addEventListener('dblclick', function () {
                applyManualDistrict(opt.getAttribute('data-district'));
            });
        });
        if (districtSearch) {
            districtSearch.addEventListener('input', function () {
                filterDistrictOptions(this.value);
            });
        }
        if (districtSubmit) {
            districtSubmit.addEventListener('click', function () {
                applyManualDistrict(pendingDistrict);
            });
        }
        document.addEventListener('keydown', function (ev) {
            if (ev.key === 'Escape' && districtModal && !districtModal.hidden) {
                closeDistrictModal();
            }
        });
    }

    function applyGpsDistrict(id) {
        if (!id) {
            return;
        }
        try {
            if (sessionStorage.getItem('ac_cal_district_manual')) {
                return;
            }
        } catch (e) {}
        var url = new URL(window.location.href);
        var current = url.searchParams.get('district') || '';
        if (String(current) === String(id)) {
            return;
        }
        if (current && current !== 'all' && url.searchParams.get('geo') !== 'ip') {
            return;
        }
        url.searchParams.set('district', id);
        url.searchParams.set('geo', 'gps');
        window.location.replace(url.toString());
    }

    var canAutoGeo = true;
    try { canAutoGeo = !sessionStorage.getItem('ac_cal_district_manual'); } catch (e) {}
    if (canAutoGeo && navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(function (pos) {
            var q = 'lat=' + encodeURIComponent(pos.coords.latitude)
                + '&lng=' + encodeURIComponent(pos.coords.longitude);
            fetch('/calendar/locate?' + q, { credentials: 'same-origin' })
                .then(function (r) { return r.json(); })
                .then(function (d) { applyGpsDistrict(d && d.district_id); })
                .catch(function () {});
        }, function () {}, {
            maximumAge: 600000,
            timeout: 8000,
            enableHighAccuracy: false,
        });
    }
})();
