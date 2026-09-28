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

    @api.model
    def report_brand_logo_data_uri(self, dark=False):
        """AuctionChamp logo as PNG data URI for PDF (wkhtmltopdf-safe).

        Uses the same brand asset as projector / registration pages
        (``static/src/assets/images/logo.svg``), rasterized so PDF engines
        that do not render SVG still show the authentic mark.

        :param dark: when True, use navy logo (for light theme footers like Lemon).
        """
        import base64
        import logging

        _logger = logging.getLogger(__name__)
        try:
            from odoo.modules.module import get_resource_path
            if dark:
                path = get_resource_path(
                    'auction_module', 'static', 'img', 'logo_navy.svg')
            else:
                path = get_resource_path(
                    'auction_module', 'static', 'src', 'assets', 'images', 'logo.svg')
            if not path:
                return ''
            with open(path, 'rb') as svg_file:
                svg_bytes = svg_file.read()
            try:
                import cairosvg
                png_bytes = cairosvg.svg2png(bytestring=svg_bytes, output_width=482)
            except Exception:
                # Fallback: embed SVG directly if cairosvg is unavailable
                return 'data:image/svg+xml;base64,' + base64.b64encode(svg_bytes).decode('ascii')
            return 'data:image/png;base64,' + base64.b64encode(png_bytes).decode('ascii')
        except Exception:
            _logger.debug('Could not load AuctionChamp brand logo for PDF', exc_info=True)
            return ''

    @api.model
    def report_roster_theme_palette(self, theme=None):
        """PDF roster color palette keyed by tournament ``player_display_template``.

        Returns a flat dict of hex colors for QWeb headers / tables / footer.
        Unknown themes fall back to Vanilla.
        """
        theme = (theme or 'vanilla').strip().lower()
        if theme == 'blackberry':
            theme = 'blueberry'
        palettes = {
            'vanilla': {
                'primary': '#5B7EB8',
                'primary_dark': '#3D5F94',
                'on_primary': '#FFFFFF',
                'muted_on_primary': '#E8EEFA',
                'ink': '#1A3560',
                'card_bg': '#F0F4FC',
                'card_border': '#C5D4F0',
                'row_alt': '#F4F7FC',
                'subtle': '#7A8DA8',
                'body': '#3A4A5E',
                'remaining': '#B8F0C8',
                'brand_dark': False,
            },
            'butterscotch': {
                'primary': '#B3801F',
                'primary_dark': '#7C531A',
                'on_primary': '#FFFFFF',
                'muted_on_primary': '#FFF7E6',
                'ink': '#241809',
                'card_bg': '#FFF8E8',
                'card_border': '#E8D4A0',
                'row_alt': '#FFFBF0',
                'subtle': '#9A7A40',
                'body': '#5A4020',
                'remaining': '#D4F0B8',
                'brand_dark': False,
            },
            'strawberry': {
                'primary': '#C2185B',
                'primary_dark': '#880E4F',
                'on_primary': '#FFFFFF',
                'muted_on_primary': '#FFD6E8',
                'ink': '#1A0A12',
                'card_bg': '#FFF5F9',
                'card_border': '#F8BBD0',
                'row_alt': '#FFF0F5',
                'subtle': '#9D174D',
                'body': '#5A3048',
                'remaining': '#C8F0D0',
                'brand_dark': False,
            },
            'cherry': {
                'primary': '#DC143C',
                'primary_dark': '#9A0F22',
                'on_primary': '#FFFFFF',
                'muted_on_primary': '#FFECEC',
                'ink': '#180405',
                'card_bg': '#FFF5F6',
                'card_border': '#E0A0A8',
                'row_alt': '#FFF0F2',
                'subtle': '#9A5060',
                'body': '#5A3038',
                'remaining': '#C8F0D0',
                'brand_dark': False,
            },
            'pistah': {
                'primary': '#2F7D32',
                'primary_dark': '#1C4D2A',
                'on_primary': '#FFFFFF',
                'muted_on_primary': '#ECFCE8',
                'ink': '#06140A',
                'card_bg': '#F2FAF0',
                'card_border': '#A7D1A0',
                'row_alt': '#F6FCF4',
                'subtle': '#5A8A55',
                'body': '#3A5A40',
                'remaining': '#C8F0B8',
                'brand_dark': False,
            },
            'lemon': {
                'primary': '#C9A400',
                'primary_dark': '#8F7400',
                'on_primary': '#1F1A0A',
                'muted_on_primary': '#3D3210',
                'ink': '#1F1A0A',
                'card_bg': '#FBF6E8',
                'card_border': '#E8DDB8',
                'row_alt': '#FFFDF5',
                'subtle': '#6E5A00',
                'body': '#5C4A14',
                'remaining': '#2F7D32',
                'brand_dark': True,
            },
            'blueberry': {
                'primary': '#2563EB',
                'primary_dark': '#1E3A8A',
                'on_primary': '#FFFFFF',
                'muted_on_primary': '#DBEAFE',
                'ink': '#050A14',
                'card_bg': '#EFF6FF',
                'card_border': '#93C5FD',
                'row_alt': '#F5F9FF',
                'subtle': '#64748B',
                'body': '#334155',
                'remaining': '#B8F0C8',
                'brand_dark': False,
            },
        }
        return dict(palettes.get(theme) or palettes['vanilla'])

    @api.model
    def report_roster_row_metrics(self, row_count):
        """Dynamic row sizing so the player table fills one A4 page.

        Fewer players → taller rows / larger photos.
        More players (up to ~20) → tighter rows so content stays on one page.
        """
        n = max(int(row_count or 1), 1)
        # Keep headroom for the larger masthead + in-flow footer on one A4 page.
        budget_px = 600
        row_h = int(budget_px / n)
        # Clamp: stay readable at 20 players, expand for smaller squads
        row_h = max(22, min(64, row_h))

        photo = max(18, min(56, row_h - 10))
        pad_y = max(2, min(18, (row_h - photo) // 2))
        pad_x = 6 if row_h >= 36 else 4

        if row_h >= 52:
            font_name, font_cell, font_role, font_points = 14, 12, 11, 15
        elif row_h >= 40:
            font_name, font_cell, font_role, font_points = 12, 10, 9, 13
        else:
            font_name, font_cell, font_role, font_points = 10, 9, 8, 11

        return {
            'row_h': row_h,
            'photo': photo,
            'pad_y': pad_y,
            'pad_x': pad_x,
            'font_name': font_name,
            'font_cell': font_cell,
            'font_role': font_role,
            'font_points': font_points,
            'photo_cell_w': photo + 8,
        }

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
