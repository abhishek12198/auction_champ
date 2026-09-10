/* global */ (function () {
    'use strict';

    var cells = document.querySelectorAll('.ac-cal-cell');
    var panels = document.querySelectorAll('.ac-cal-day-panel');
    if (!cells.length) {
        return;
    }

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
})();
