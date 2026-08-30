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
#  This source code, including but not limited to its algorithms, business
#  logic, database structures, models, controllers, views, reports, templates,
#  APIs, documentation, and related materials, constitutes proprietary and
#  confidential information owned exclusively by AuctionChamp.
#
#  This software is protected by applicable copyright laws and international
#  intellectual property treaties. Unauthorized copying, reproduction,
#  modification, distribution, publication, sublicensing, reverse engineering,
#  decompilation, disassembly, disclosure, or use of this software, in whole
#  or in part, is strictly prohibited without the prior written permission of
#  AuctionChamp.
#
#  This software is licensed, not sold. Possession of the source code does not
#  grant any right to copy, modify, redistribute, or create derivative works
#  except as expressly permitted under a valid written license agreement with
#  AuctionChamp.
#
#  Any unauthorized use may result in civil and criminal penalties under
#  applicable intellectual property and copyright laws.
#
#  Company  : AuctionChamp
#  Website  : www.auctionchamp.live
#  Email    : auctionchamp.live@gmail.com
#
#  © 2026 AuctionChamp. All Rights Reserved.
#
##############################################################################

import math

from odoo import api, models, fields, _
from odoo.osv import expression

PAGE_SIZE_DEFAULT = 80


class AuctionHistory(models.Model):

    _name = 'auction.history'
    _description = 'Auction History'
    _inherit = ['auction.tournament.security.mixin', 'auction.live.snapshot.mixin']
    _order = 'create_date desc, id desc'

    active = fields.Boolean(default=True)
    team_id = fields.Many2one('auction.team', 'Team')
    player_id = fields.Many2one(
        'auction.team.player',
        string='Player',
        ondelete='set null',
        index=True,
        help='Player this history row refers to. Used to redact Mystery sales until reveal.',
    )
    player_photo = fields.Binary()
    message = fields.Char("History Message")
    tournament_id = fields.Many2one('auction.tournament', 'Tournament', index=True)

    # ── Custom history board (tournament UI) ──────────────────────────────

    @api.model
    def get_history_board(
        self,
        tournament_id,
        page=1,
        page_size=PAGE_SIZE_DEFAULT,
        search='',
        event_filter='all',
    ):
        """Paginated payload for the custom auction-history client action.

        Returns player photo, serial, sold team + logo, sold points / units,
        and timestamp — 80 rows per page by default (Odoo list-style pager).
        """
        tournament_id = int(tournament_id or 0)
        if not tournament_id:
            return self._empty_board_payload()

        tournament = self.env['auction.tournament'].browse(tournament_id).exists()
        if not tournament:
            return self._empty_board_payload()

        try:
            page = max(1, int(page or 1))
        except (TypeError, ValueError):
            page = 1
        try:
            page_size = int(page_size or PAGE_SIZE_DEFAULT)
        except (TypeError, ValueError):
            page_size = PAGE_SIZE_DEFAULT
        if page_size < 1:
            page_size = PAGE_SIZE_DEFAULT
        page_size = min(page_size, 200)

        event_filter = (event_filter or 'all').strip().lower()
        if event_filter not in ('all', 'sold', 'unsold', 'other'):
            event_filter = 'all'

        domain = [('tournament_id', '=', tournament_id)]
        if event_filter == 'sold':
            domain.append(('team_id', '!=', False))
        elif event_filter == 'unsold':
            domain = expression.AND([domain, [
                ('team_id', '=', False),
                ('message', 'ilike', 'unsold'),
            ]])
        elif event_filter == 'other':
            domain = expression.AND([domain, [
                ('team_id', '=', False),
                '!', ('message', 'ilike', 'unsold'),
            ]])

        search = (search or '').strip()
        if search:
            name_domain = [
                '|', '|',
                ('message', 'ilike', search),
                ('player_id.name', 'ilike', search),
                ('team_id.name', 'ilike', search),
            ]
            if search.isdigit():
                name_domain = expression.OR([
                    name_domain,
                    [('player_id.sl_no', '=', int(search))],
                ])
            domain = expression.AND([domain, name_domain])

        History = self.with_context(auction_skip_tournament_security=True)
        total = History.search_count(domain)
        total_pages = max(1, int(math.ceil(float(total) / float(page_size)))) if total else 1
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * page_size
        rows = History.search(
            domain,
            order='create_date desc, id desc',
            limit=page_size,
            offset=offset,
        )

        player_ids = rows.mapped('player_id').ids
        points_map = {}
        if player_ids:
            SaleLine = self.env['auction.auction.player'].sudo().with_context(
                auction_skip_tournament_security=True,
            )
            for line in SaleLine.search(
                [('player_id', 'in', player_ids)],
                order='id desc',
            ):
                pid = line.player_id.id
                if pid not in points_map:
                    points_map[pid] = int(line.points or 0)

        history_photo_ids = set()
        team_logo_ids = set()
        player_photo_ids = set()
        if rows:
            # Binary fields are attachment-backed — no DB columns on the main table.
            self.env.cr.execute(
                """
                SELECT res_id FROM ir_attachment
                 WHERE res_model = 'auction.history'
                   AND res_field = 'player_photo'
                   AND res_id = ANY(%s)
                """,
                (list(rows.ids),),
            )
            history_photo_ids = {r[0] for r in self.env.cr.fetchall()}

        team_ids = rows.mapped('team_id').ids
        if team_ids:
            self.env.cr.execute(
                """
                SELECT res_id FROM ir_attachment
                 WHERE res_model = 'auction.team'
                   AND res_field = 'logo'
                   AND res_id = ANY(%s)
                """,
                (team_ids,),
            )
            team_logo_ids = {r[0] for r in self.env.cr.fetchall()}

        if player_ids:
            self.env.cr.execute(
                """
                SELECT res_id FROM ir_attachment
                 WHERE res_model = 'auction.team.player'
                   AND res_field = 'photo'
                   AND res_id = ANY(%s)
                """,
                (player_ids,),
            )
            player_photo_ids = {r[0] for r in self.env.cr.fetchall()}

        unit_js = tournament.get_point_unit_js() if hasattr(tournament, 'get_point_unit_js') else {}
        records = []
        for rec in rows:
            player = rec.player_id
            team = rec.team_id
            msg = (rec.message or '').strip()
            msg_l = msg.lower()
            if team:
                event = 'sold'
            elif 'unsold' in msg_l:
                event = 'unsold'
            else:
                event = 'other'

            sold_points = points_map.get(player.id, 0) if player else 0
            if rec.id in history_photo_ids:
                photo_url = '/web/image/auction.history/%s/player_photo' % rec.id
            elif player and player.id in player_photo_ids:
                photo_url = '/web/image/auction.team.player/%s/photo' % player.id
            else:
                photo_url = ''

            points_display = ''
            if event == 'sold' and sold_points:
                try:
                    points_display = tournament.format_points(sold_points)
                except Exception:
                    points_display = '{:,}'.format(sold_points)

            create_dt = fields.Datetime.context_timestamp(
                rec, rec.create_date,
            ) if rec.create_date else False

            records.append({
                'id': rec.id,
                'event': event,
                'message': msg,
                'player_id': player.id if player else False,
                'player_name': (player.name or '') if player else self._name_from_message(msg),
                'sl_no': player.sl_no if player else False,
                'photo_url': photo_url,
                'team_id': team.id if team else False,
                'team_name': (team.name or '') if team else '',
                'team_logo_url': (
                    '/web/image/auction.team/%s/logo' % team.id
                    if team and team.id in team_logo_ids else ''
                ),
                'sold_points': sold_points if event == 'sold' else 0,
                'points_display': points_display,
                'create_date': fields.Datetime.to_string(rec.create_date) if rec.create_date else '',
                'timestamp': create_dt.strftime('%d %b %Y · %I:%M %p') if create_dt else '',
                'timestamp_short': create_dt.strftime('%I:%M %p').lstrip('0') if create_dt else '',
                'date_label': create_dt.strftime('%d %b %Y') if create_dt else '',
            })

        start = offset + 1 if total else 0
        end = min(offset + page_size, total)
        return {
            'tournament_id': tournament.id,
            'tournament_name': tournament.name or '',
            'unit': unit_js,
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages,
            'start': start,
            'end': end,
            'search': search,
            'event_filter': event_filter,
            'records': records,
        }

    @api.model
    def _empty_board_payload(self):
        return {
            'tournament_id': False,
            'tournament_name': '',
            'unit': {},
            'page': 1,
            'page_size': PAGE_SIZE_DEFAULT,
            'total': 0,
            'total_pages': 1,
            'start': 0,
            'end': 0,
            'search': '',
            'event_filter': 'all',
            'records': [],
        }

    @staticmethod
    def _name_from_message(message):
        """Best-effort player name when player_id is missing."""
        msg = (message or '').strip()
        if not msg:
            return ''
        for sep in (' sold to ', ' is Unsold', ' sale corrected', ' Points updated for '):
            if sep.lower() in msg.lower():
                idx = msg.lower().find(sep.lower())
                return msg[:idx].strip()
        return msg[:48]


