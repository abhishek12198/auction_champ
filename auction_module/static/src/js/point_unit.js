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

    global.AuctionPointUnit = {
        format: format,
        formatHtml: formatHtml,
        formatNumber: formatNumber,
        symbol: symbol,
        name: name,
        setConfig: setConfig,
        cfg: cfg,
    };

    // Convenience aliases used by consoles
    global.fmtUnit = format;
    global.fmtUnitHtml = formatHtml;
    global.fmtUnitNum = formatNumber;
    global.pointUnitSymbol = symbol;
    global.pointUnitName = name;
})(typeof window !== 'undefined' ? window : this);
