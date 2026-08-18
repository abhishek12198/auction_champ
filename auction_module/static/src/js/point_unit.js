/* global window */
/**
 * Tournament player-value unit formatter.
 *
 * Expects optional config:
 *   window.AC_POINT_UNIT = { name, symbol, position: 'before'|'after', with_space: bool }
 *
 * Defaults to PTS after the number (legacy behaviour).
 */
(function (global) {
    'use strict';

    var DEFAULT = {
        name: 'Points',
        symbol: 'PTS',
        position: 'after',
        with_space: true,
    };

    function cfg() {
        var c = global.AC_POINT_UNIT || DEFAULT;
        return {
            name: c.name || DEFAULT.name,
            symbol: c.symbol || DEFAULT.symbol,
            position: c.position === 'before' ? 'before' : 'after',
            with_space: c.with_space !== false && c.with_space !== 0,
        };
    }

    function numStr(n, useLocale) {
        var num = Number(n);
        if (!isFinite(num)) num = 0;
        if (useLocale === false) return String(Math.trunc(num));
        try {
            return Math.trunc(num).toLocaleString();
        } catch (e) {
            return String(Math.trunc(num));
        }
    }

    /** Format amount with unit symbol, e.g. "1,000 PTS" or "₹1000". */
    function format(amount, useLocale) {
        var c = cfg();
        var n = numStr(amount, useLocale !== false);
        var sep = c.with_space ? ' ' : '';
        if (c.position === 'before') {
            return c.symbol + sep + n;
        }
        return n + sep + c.symbol;
    }

    /**
     * Format with a wrapped unit span for styled displays.
     * unitClass — CSS class on the symbol span (optional).
     */
    function formatHtml(amount, unitClass, useLocale) {
        var c = cfg();
        var n = numStr(amount, useLocale !== false);
        var sep = c.with_space ? ' ' : '';
        var cls = unitClass ? String(unitClass) : '';
        var unit = '<span class="' + cls + '">' + String(c.symbol)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;') + '</span>';
        if (c.position === 'before') {
            return unit + sep + n;
        }
        return n + sep + unit;
    }

    /** Numeric part only (locale). */
    function formatNumber(amount) {
        return numStr(amount, true);
    }

    function symbol() {
        return cfg().symbol;
    }

    function name() {
        return cfg().name;
    }

    function setConfig(obj) {
        if (!obj || typeof obj !== 'object') return;
        global.AC_POINT_UNIT = Object.assign({}, cfg(), obj);
    }

    var SMALL = [
        'Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine',
        'Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen', 'Sixteen',
        'Seventeen', 'Eighteen', 'Nineteen',
    ];
    var TENS = [
        '', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety',
    ];

    function belowHundred(n) {
        if (n < 20) {
            return SMALL[n];
        }
        var t = Math.floor(n / 10);
        var o = n % 10;
        return o ? TENS[t] + ' ' + SMALL[o] : TENS[t];
    }

    function belowThousand(n) {
        if (n < 100) {
            return belowHundred(n);
        }
        var h = Math.floor(n / 100);
        var r = n % 100;
        return SMALL[h] + ' Hundred' + (r ? ' ' + belowHundred(r) : '');
    }

    /**
     * Indian numbering: Thousand / Lakh / Crore.
     * 10000 → "Ten Thousand"
     */
    function toWords(amount) {
        var n = Math.trunc(Math.abs(Number(amount) || 0));
        if (!isFinite(n)) {
            n = 0;
        }
        if (n === 0) {
            return 'Zero';
        }
        if (n >= 1e12) {
            return numStr(n, true);
        }
        var parts = [];
        var crore = Math.floor(n / 10000000);
        n %= 10000000;
        var lakh = Math.floor(n / 100000);
        n %= 100000;
        var thousand = Math.floor(n / 1000);
        var rest = n % 1000;
        if (crore) {
            parts.push(toWords(crore) + ' Crore');
        }
        if (lakh) {
            parts.push(belowThousand(lakh) + ' Lakh');
        }
        if (thousand) {
            parts.push(belowThousand(thousand) + ' Thousand');
        }
        if (rest) {
            parts.push(belowThousand(rest));
        }
        return parts.join(' ');
    }

    function singularUnit(unitName) {
        var u = String(unitName || 'Points').trim() || 'Points';
        if (/^points$/i.test(u)) {
            return 'Point';
        }
        if (/ies$/i.test(u)) {
            return u.replace(/ies$/i, 'y');
        }
        if (/s$/i.test(u) && !/ss$/i.test(u)) {
            return u.replace(/s$/i, '');
        }
        return u;
    }

    function pluralUnit(unitName) {
        var u = String(unitName || 'Points').trim() || 'Points';
        if (/^points$/i.test(u) || /^point$/i.test(u)) {
            return 'Points';
        }
        if (/s$/i.test(u)) {
            return u;
        }
        var s = singularUnit(u);
        if (/[sxz]$/i.test(s) || /(ch|sh)$/i.test(s)) {
            return s + 'es';
        }
        if (/y$/i.test(s) && !/[aeiou]y$/i.test(s)) {
            return s.slice(0, -1) + 'ies';
        }
        return s + 's';
    }

    function unitLabel(amount, unitName) {
        var n = Math.trunc(Math.abs(Number(amount) || 0));
        var unit = unitName || name();
        return n === 1 ? singularUnit(unit) : pluralUnit(unit);
    }

    /** e.g. 10000 → "Ten Thousand Points" */
    function formatWords(amount, unitName) {
        return toWords(amount) + ' ' + unitLabel(amount, unitName);
    }

    global.AuctionPointUnit = {
        format: format,
        formatHtml: formatHtml,
        formatNumber: formatNumber,
        symbol: symbol,
        name: name,
        setConfig: setConfig,
        cfg: cfg,
        toWords: toWords,
        formatWords: formatWords,
        unitLabel: unitLabel,
    };

    // Convenience aliases used by consoles
    global.fmtUnit = format;
    global.fmtUnitHtml = formatHtml;
    global.fmtUnitNum = formatNumber;
    global.pointUnitSymbol = symbol;
    global.pointUnitName = name;
})(typeof window !== 'undefined' ? window : this);
