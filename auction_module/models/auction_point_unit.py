# -*- coding: utf-8 -*-
##############################################################################
#
#  AuctionChamp - Professional Sports Auction Management Platform
#
#  Copyright (c) 2026 AuctionChamp.
#  All Rights Reserved.
#
#  CONFIDENTIAL & PROPRIETARY
#
#  Company  : AuctionChamp
#  Website  : www.auctionchamp.live
#  Email    : auctionchamp.live@gmail.com
#
#  © 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

from odoo import api, fields, models


class AuctionPointUnit(models.Model):
    _name = 'auction.point.unit'
    _description = 'Auction Point / Value Unit'
    _order = 'sequence, name'

    name = fields.Char(
        string='Unit Name',
        required=True,
        help='Label used in headers and reports (e.g. Points, Rupees).',
    )
    symbol = fields.Char(
        string='Symbol / Sign',
        required=True,
        help='Shown next to numeric values on screens (e.g. PTS, ₹, $, Rs).',
    )
    report_symbol = fields.Char(
        string='PDF / Report Symbol',
        help='Optional symbol used in printed PDFs. Use this when the screen '
             'symbol (e.g. ₹) does not render in PDF fonts. '
             'Leave empty to auto-map ₹ → Rs. and keep other symbols as-is.',
    )
    position = fields.Selection(
        [
            ('before', 'Before value'),
            ('after', 'After value'),
        ],
        string='Symbol Position',
        required=True,
        default='after',
        help='Whether the symbol/sign appears before or after the numeric value.',
    )
    with_space = fields.Boolean(
        string='Space Between',
        default=True,
        help='Insert a space between the symbol and the number. '
             'Usually on for PTS (1000 PTS), off for currency signs (₹1000).',
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    def _pdf_safe_symbol(self, symbol=None):
        """Symbol used in PDF reports (optional report_symbol override)."""
        self.ensure_one()
        if self.report_symbol:
            return self.report_symbol
        return symbol if symbol is not None else (self.symbol or '')

    @staticmethod
    def _as_html_entities(text):
        """Encode non-ASCII chars as numeric HTML entities.

        Prevents UTF-8 mojibake (e.g. ₹ → â‚¹) when wkhtmltopdf / an
        intermediate layer mis-handles document encoding.
        """
        parts = []
        for ch in text or '':
            code = ord(ch)
            if code < 128:
                # Escape HTML-significant ASCII just in case
                if ch == '&':
                    parts.append('&amp;')
                elif ch == '<':
                    parts.append('&lt;')
                elif ch == '>':
                    parts.append('&gt;')
                else:
                    parts.append(ch)
            else:
                parts.append('&#%d;' % code)
        return ''.join(parts)

    def format_value(self, amount, use_locale=True, for_pdf=False):
        """Return a display string for ``amount`` using this unit."""
        self.ensure_one()
        from markupsafe import Markup
        try:
            num = int(amount or 0)
        except (TypeError, ValueError):
            num = 0
        num_str = '{:,}'.format(num) if use_locale else str(num)
        sep = ' ' if self.with_space else ''
        symbol = self._pdf_safe_symbol() if for_pdf else (self.symbol or '')
        if for_pdf:
            # Entity-encode symbol so ₹ survives PDF HTML encoding pipelines.
            symbol = self._as_html_entities(symbol)
            if self.position == 'before':
                return Markup('%s%s%s' % (symbol, sep, num_str))
            return Markup('%s%s%s' % (num_str, sep, symbol))
        if self.position == 'before':
            return '%s%s%s' % (symbol, sep, num_str)
        return '%s%s%s' % (num_str, sep, symbol)

    @api.model
    def report_unicode_font_css(self):
        """CSS embedding DejaVu Sans so ₹ / Unicode unit signs render in PDF."""
        import base64
        from markupsafe import Markup
        from odoo.modules.module import get_resource_path

        chunks = []
        for fname, weight in (
            ('DejaVuSans.ttf', 'normal'),
            ('DejaVuSans-Bold.ttf', 'bold'),
        ):
            path = get_resource_path('auction_module', 'static', 'fonts', fname)
            if not path:
                continue
            with open(path, 'rb') as font_file:
                b64 = base64.b64encode(font_file.read()).decode('ascii')
            chunks.append(
                "@font-face{"
                "font-family:'AuctionUnitFont';"
                "src:url(data:font/truetype;charset=utf-8;base64,%s) format('truetype');"
                "font-weight:%s;font-style:normal;}"
                % (b64, weight)
            )
        chunks.append(
            ".ac-unit-val{font-family:'AuctionUnitFont','DejaVu Sans',sans-serif !important;}"
        )
        return Markup(''.join(chunks))

    def to_js_dict(self):
        """Payload for frontend formatters."""
        self.ensure_one()
        return {
            'id': self.id,
            'name': self.name or 'Points',
            'symbol': self.symbol or 'PTS',
            'position': self.position or 'after',
            'with_space': bool(self.with_space),
        }

    @api.model
    def default_unit(self):
        """Return the master PTS unit (xmlid), creating a fallback if missing.

        Safe during registry init: if the table is not ready yet, return an
        empty recordset instead of querying/creating.
        """
        cr = self.env.cr
        # Table may not exist yet while models are being `_auto_init`'d.
        cr.execute(
            "SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'auction_point_unit' LIMIT 1"
        )
        if not cr.fetchone():
            return self.browse()

        unit = self.env.ref('auction_module.point_unit_pts', raise_if_not_found=False)
        if unit:
            return unit.sudo()
        unit = self.sudo().with_context(active_test=False).search(
            [('symbol', '=', 'PTS')], limit=1
        )
        if unit:
            return unit
        # Fallback only when master data is not loaded yet.
        return self.sudo().create({
            'name': 'Points',
            'symbol': 'PTS',
            'position': 'after',
            'with_space': True,
            'sequence': 1,
        })
