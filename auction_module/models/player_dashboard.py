# -*- coding: utf-8 -*-
from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models


class AuctionTeamPlayerDashboard(models.Model):
    _inherit = 'auction.team.player'

    @api.model
    def get_player_dashboard_data(self, tournament_id=None):
        """Player Dashboard payload — same navbar tournament as Players list."""
        env = self.env
        Tournament = env['auction.tournament'].sudo().with_context(active_test=False)
        user = env.user.sudo().with_context(active_test=False)

        tournament = Tournament.browse()
        if tournament_id:
            try:
                tid = int(tournament_id)
            except (TypeError, ValueError):
                tid = 0
            if tid:
                tournament = Tournament.browse(tid).exists()
        if not tournament:
            get_working = getattr(user, 'get_working_tournament', None)
            if callable(get_working):
                try:
                    tournament = get_working()
                except Exception:
                    tournament = Tournament.browse()
        if not tournament:
            tournament = user.tournament_id or user.tournament_ids[:1]

        Player = env['auction.team.player'].sudo().with_context(
            auction_skip_tournament_security=True,
        )
        AucPlayer = env['auction.auction.player'].sudo().with_context(
            auction_skip_tournament_security=True,
        )

        def pub_img(model, rec_id, field):
            return '/auction/public/image/%s/%d/%s' % (model, rec_id, field)

        def fmt_create(value):
            if not value:
                return ''
            if hasattr(value, 'strftime'):
                return value.strftime('%d %b %Y')
            raw = str(value)
            try:
                return datetime.strptime(raw[:10], '%Y-%m-%d').strftime('%d %b %Y')
            except (TypeError, ValueError):
                return raw[:10]

        def group_counts(domain, groupby_field):
            out = {}
            for g in Player.read_group(domain, [groupby_field], [groupby_field], lazy=False):
                out[g.get(groupby_field)] = g.get('__count') or 0
            return out

        t_domain = (
            [('tournament_id', '=', tournament.id)]
            if tournament else [('id', '=', False)]
        )

        states = ['draft', 'auction', 'sold', 'unsold']
        state_counts = {s: 0 for s in states}
        for key, n in group_counts(t_domain, 'state').items():
            if key in state_counts:
                state_counts[key] = n
        total = sum(state_counts.values())

        tournament_type = (tournament.tournament_type if tournament else 'cricket') or 'cricket'
        is_football = tournament_type == 'football'

        last_draft = Player.search_read(
            t_domain + [('state', '=', 'draft')],
            ['name', 'role', 'tier_id', 'base_price', 'create_date', 'dominant_position_id'],
            order='create_date desc',
            limit=10,
        )
        draft_ids = [row['id'] for row in last_draft]
        draft_photo_ids = set(Player.search([
            ('id', 'in', draft_ids or [0]),
            ('photo', '!=', False),
        ]).ids) if draft_ids else set()
        draft_players = []
        for p in last_draft:
            if is_football:
                pos = p.get('dominant_position_id')
                display_role = (pos[1] if pos else '') or (p.get('role') or '')
            else:
                display_role = p.get('role') or ''
            tier = p.get('tier_id')
            draft_players.append({
                'name': p.get('name') or '',
                'role': display_role,
                'tier': tier[1] if tier else '',
                'base_price': p.get('base_price') or 0,
                'photo_url': pub_img('auction.team.player', p['id'], 'photo') if p['id'] in draft_photo_ids else '',
                'create_date': fmt_create(p.get('create_date')),
            })

        tz = pytz.timezone('Asia/Kolkata')
        today_local = datetime.now(tz).date()
        day_labels = []
        day_keys = {}
        for i in range(4, -1, -1):
            day = today_local - timedelta(days=i)
            day_labels.append(day)
            day_keys[day.isoformat()] = day.strftime('%d %b')
        range_start = tz.localize(datetime(
            day_labels[0].year, day_labels[0].month, day_labels[0].day, 0, 0, 0,
        )).astimezone(pytz.utc).replace(tzinfo=None)
        daily_counts = {day.strftime('%d %b'): 0 for day in day_labels}
        try:
            day_groups = Player.read_group(
                t_domain + [('create_date', '>=', fields.Datetime.to_string(range_start))],
                ['create_date'],
                ['create_date:day'],
                lazy=False,
            )
            for g in day_groups:
                raw = g.get('create_date:day') or g.get('create_date')
                iso = ''
                if hasattr(raw, 'strftime'):
                    iso = raw.strftime('%Y-%m-%d')
                elif isinstance(raw, str) and len(raw) >= 10:
                    iso = raw[:10]
                label = day_keys.get(iso)
                if label:
                    daily_counts[label] += g.get('__count') or 0
        except Exception:
            pass
        daily = [{'label': day.strftime('%d %b'), 'count': daily_counts[day.strftime('%d %b')]}
                 for day in day_labels]

        role_counts = {}
        for key, n in group_counts(t_domain, 'role').items():
            role = ((key or 'Unknown') if isinstance(key, str) else 'Unknown')
            role = (role or 'Unknown').strip() or 'Unknown'
            role_counts[role] = role_counts.get(role, 0) + n
        position_counts = {}
        if is_football:
            for key, n in group_counts(t_domain, 'dominant_position_id').items():
                pos_name = (key[1] if key else 'Unknown')
                pos_name = (pos_name or 'Unknown').strip() or 'Unknown'
                position_counts[pos_name] = position_counts.get(pos_name, 0) + n
        tier_counts = {}
        for key, n in group_counts(t_domain, 'tier_id').items():
            tier_name = key[1] if key else 'No Tier'
            tier_counts[tier_name] = tier_counts.get(tier_name, 0) + n
        team_counts = {}
        for key, n in group_counts(t_domain, 'assigned_team_id').items():
            if not key:
                continue
            team_counts[key[1] or 'Unknown'] = team_counts.get(key[1] or 'Unknown', 0) + n

        icon_count = sum(n for key, n in group_counts(t_domain, 'icon_player').items() if key)
        paid_count = unpaid_count = 0
        for key, n in group_counts(t_domain, 'amount_paid').items():
            if key:
                paid_count += n
            else:
                unpaid_count += n

        icon_rows = Player.search_read(
            t_domain + [('icon_player', '=', True)],
            ['name', 'role', 'tier_id', 'assigned_team_id', 'dominant_position_id'],
            order='assigned_team_id, name',
        )
        icon_ids = [row['id'] for row in icon_rows]
        icon_photo_ids = set(Player.search([
            ('id', 'in', icon_ids or [0]),
            ('photo', '!=', False),
        ]).ids) if icon_ids else set()
        team_ids = [
            row['assigned_team_id'][0]
            for row in icon_rows
            if row.get('assigned_team_id')
        ]
        team_logo_ids = set()
        if team_ids:
            team_logo_ids = set(env['auction.team'].sudo().with_context(
                auction_skip_tournament_security=True,
            ).search([
                ('id', 'in', team_ids),
                ('logo', '!=', False),
            ]).ids)
        icon_points = {}
        if icon_ids:
            for line in AucPlayer.search_read(
                [('player_id', 'in', icon_ids)],
                ['player_id', 'points'],
                order='points desc',
            ):
                pid = line['player_id'][0] if line.get('player_id') else False
                if pid and pid not in icon_points:
                    icon_points[pid] = line.get('points') or 0
        icon_list = []
        for p in icon_rows:
            if is_football:
                pos = p.get('dominant_position_id')
                display_role = (pos[1] if pos else '') or (p.get('role') or '')
            else:
                display_role = p.get('role') or ''
            team = p.get('assigned_team_id')
            team_id = team[0] if team else False
            tier = p.get('tier_id')
            icon_list.append({
                'name': p.get('name') or '',
                'role': display_role,
                'tier': tier[1] if tier else '',
                'team': team[1] if team else 'Unassigned',
                'team_logo': pub_img('auction.team', team_id, 'logo')
                             if team_id and team_id in team_logo_ids else '',
                'points': icon_points.get(p['id'], 0),
                'photo_url': pub_img('auction.team.player', p['id'], 'photo') if p['id'] in icon_photo_ids else '',
            })

        def _ref(xml_id):
            try:
                return env.ref('auction_module.' + xml_id).id
            except Exception:
                return False

        logo = ''
        if tournament and env['auction.tournament'].sudo().with_context(
            auction_skip_tournament_security=True,
            active_test=False,
        ).search_count([('id', '=', tournament.id), ('logo', '!=', False)]):
            logo = pub_img('auction.tournament', tournament.id, 'logo')

        return {
            'total': total,
            'state_counts': state_counts,
            'icon_count': icon_count,
            'paid_count': paid_count,
            'unpaid_count': unpaid_count,
            'draft_players': draft_players,
            'daily': daily,
            'roles': [{'label': k, 'count': v} for k, v in sorted(role_counts.items(), key=lambda x: -x[1])],
            'positions': [{'label': k, 'count': v} for k, v in sorted(position_counts.items(), key=lambda x: -x[1])],
            'tournament_type': tournament_type,
            'tiers': [{'label': k, 'count': v} for k, v in sorted(tier_counts.items(), key=lambda x: -x[1])],
            'team_player_counts': [
                {'label': k, 'count': v} for k, v in sorted(team_counts.items(), key=lambda x: -x[1])
            ],
            'icon_players': icon_list,
            'tournament_id': tournament.id if tournament else None,
            'tournament_name': (tournament.name or '') if tournament else '',
            'tournament_logo': logo,
            'tournaments': [],
            'show_tournament_filter': False,
            'view_ids': {
                'kanban': _ref('view_auction_team_player_kanban'),
                'list': _ref('view_auction_team_player_tree'),
            },
        }
