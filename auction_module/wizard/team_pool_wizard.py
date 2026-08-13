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

# wizard/team_pool_wizard.py
import json
import random
from odoo import models, fields, api
from odoo.exceptions import UserError


class TeamPoolNameLine(models.TransientModel):
    _name = 'auction.team.pool.name.line'
    _description = 'Pool Custom Name Line'
    _order = 'pool_index asc'

    wizard_id = fields.Many2one('auction.team.pool.wizard', ondelete='cascade')
    pool_index = fields.Integer(string='#', readonly=True)
    default_label = fields.Char(string='Default', readonly=True)
    custom_name = fields.Char(string='Pool Name', required=True)


class TeamPoolWizard(models.TransientModel):
    _name = 'auction.team.pool.wizard'
    _description = 'Team Pool Generator'

    team_ids = fields.Many2many('auction.team', string='Select Teams', required=True)
    selected_team_count = fields.Integer(string='No of Teams Selected', required=True)
    pool_count = fields.Integer(string='Number of Pools', required=True, default=2)
    pool_name_ids = fields.One2many(
        'auction.team.pool.name.line', 'wizard_id', string='Pool Names',
    )
    # Stores the generated draw as JSON so renaming doesn't reshuffle teams
    pool_structure_json = fields.Text(readonly=True)
    result_html = fields.Html(string='Pool Result', readonly=True, sanitize=False)

    # ── fixture fields ────────────────────────────────────────────────────
    fixture_type = fields.Selection([
        ('pool_rr',       'Pool Round Robin (teams play within pool)'),
        ('cross_pool_rr', 'Cross Pool Round Robin (teams play outside pool)'),
        ('custom_outside','Custom Outside Pool Count (each team plays N teams outside pool)'),
    ], string='Fixture Type', default='pool_rr')
    outside_pool_count = fields.Integer(
        string='Matches per Team (League)',
        default=1,
        help='How many league matches each team should play. '
             'Default = (teams in that team\'s pool) − 1. '
             'Opponents are chosen randomly from the eligible pool for the selected fixture type.',
    )
    fixture_html = fields.Html(string='Fixture Schedule', readonly=True, sanitize=False)

    # ── helpers ──────────────────────────────────────────────────────────

    def _pool_label(self, index):
        """Return 'Pool A', 'Pool B' … 'Pool Z', 'Pool AA' … for any index."""
        n = index - 1
        label = ''
        while True:
            label = chr(65 + (n % 26)) + label
            n = n // 26 - 1
            if n < 0:
                break
        return 'Pool ' + label

    def _name_line_vals(self, index):
        default = self._pool_label(index)
        return {'pool_index': index, 'default_label': default, 'custom_name': default}

    def _prefetch_teams(self, teams_recordset):
        """Batch-fetch all fields needed for pool rendering in two queries (teams + tournaments)."""
        teams_recordset.read(['name', 'logo', 'tournament_id'])
        tournament_ids = teams_recordset.mapped('tournament_id')
        if tournament_ids:
            tournament_ids.read(['name'])

    # ── default_get: create REAL DB records so edits always persist ──────

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        count = defaults.get('pool_count', 2)
        defaults['pool_name_ids'] = [
            (0, 0, self._name_line_vals(i)) for i in range(1, count + 1)
        ]
        return defaults

    # ── onchange handlers ─────────────────────────────────────────────────

    @api.onchange('team_ids')
    def onchange_team_ids(self):
        if self.team_ids:
            self.selected_team_count = len(self.team_ids)

    @api.onchange('pool_count')
    def _onchange_pool_count(self):
        new_count = self.pool_count or 0
        # Preserve existing names by position; add/drop as needed
        existing = sorted(self.pool_name_ids, key=lambda l: l.pool_index)
        existing_names = [l.custom_name for l in existing]

        cmds = [(5, 0, 0)]
        for i in range(1, new_count + 1):
            default = self._pool_label(i)
            name = existing_names[i - 1] if i <= len(existing_names) else default
            cmds.append((0, 0, {
                'pool_index': i,
                'default_label': default,
                'custom_name': name,
            }))
        self.pool_name_ids = cmds

    # ── pool label map ────────────────────────────────────────────────────

    def _get_pool_labels(self):
        """Return {pool_index: display_name} from current pool_name_ids."""
        return {
            line.pool_index: (line.custom_name or '').strip() or line.default_label
            for line in self.pool_name_ids
        }

    # ── shared HTML renderer ──────────────────────────────────────────────

    def _render_html(self, pools, pool_labels):
        all_teams = [t for pool in pools for t in pool]
        tournament_name = (
            all_teams[0].tournament_id.name
            if all_teams and all_teams[0].tournament_id else 'Pool Draw'
        )
        max_teams = max(len(p) for p in pools)
        colors = ['#1565C0', '#B71C1C', '#2E7D32', '#6A1B9A',
                  '#E65100', '#006064', '#880E4F', '#37474F']

        wrap_s    = ('background:#0d0d2b;padding:32px 28px 36px;border-radius:16px;'
                     'font-family:Segoe UI,Arial,sans-serif;display:block;'
                     'width:100%;box-sizing:border-box;')
        title_s   = ('display:block;text-align:center;color:#FFD54F;font-size:1.4rem;'
                     'font-weight:800;letter-spacing:6px;text-transform:uppercase;margin-bottom:6px;')
        divider_s = ('display:block;width:80px;height:4px;background:#FFD54F;'
                     'margin:0 auto 20px;border-radius:2px;')
        grid_s    = 'display:flex;width:100%;'

        def hdr(color):
            return (f'display:block;flex:1;background:{color};color:#FFD54F;text-align:center;'
                    f'font-size:1rem;font-weight:800;letter-spacing:2px;'
                    f'padding:12px 8px;border-right:3px solid #0d0d2b;box-sizing:border-box;')

        def dcell():
            return ('display:block;flex:1;padding:9px 12px;'
                    'border-right:1px solid rgba(255,255,255,0.1);'
                    'border-bottom:1px solid rgba(255,255,255,0.1);'
                    'background:rgba(255,255,255,0.05);box-sizing:border-box;')

        def ecell():
            return ('display:block;flex:1;padding:9px 12px;'
                    'border-right:1px solid rgba(255,255,255,0.06);'
                    'border-bottom:1px solid rgba(255,255,255,0.06);'
                    'background:rgba(255,255,255,0.02);box-sizing:border-box;')

        header_cells = ''
        for i, pool in enumerate(pools, start=1):
            label = pool_labels.get(i, self._pool_label(i))
            color = colors[(i - 1) % len(colors)]
            header_cells += f'<div style="{hdr(color)}">{label}</div>'

        team_rows = ''
        for row in range(max_teams):
            cells = ''
            for pool in pools:
                if row < len(pool):
                    team = pool[row]
                    if team.logo:
                        b64 = team.logo.decode('utf-8') if isinstance(team.logo, bytes) else team.logo
                        img = (f'<img src="data:image/png;base64,{b64}" '
                               f'style="height:20px;width:20px;object-fit:contain;'
                               f'border-radius:3px;margin-right:8px;display:inline-block;'
                               f'vertical-align:middle;"/>')
                    else:
                        ini = ''.join(w[0].upper() for w in team.name.split()[:2])
                        img = (f'<span style="display:inline-block;height:20px;width:20px;'
                               f'background:#ffffff30;border-radius:3px;font-size:8px;'
                               f'font-weight:800;color:#fff;margin-right:8px;'
                               f'vertical-align:middle;text-align:center;line-height:20px;">'
                               f'{ini}</span>')
                    name = (f'<span style="color:#fff;font-size:.95rem;font-weight:600;'
                            f'vertical-align:middle;">{team.name}</span>')
                    cells += f'<div style="{dcell()}">{img}{name}</div>'
                else:
                    cells += f'<div style="{ecell()}"></div>'
            team_rows += f'<div style="{grid_s}">{cells}</div>'

        return (
            f'<div style="{wrap_s}">'
            f'<div style="{title_s}">{tournament_name}</div>'
            f'<div style="{divider_s}"></div>'
            f'<div style="{grid_s}">{header_cells}</div>'
            f'{team_rows}'
            f'</div>'
        )

    # ── actions ───────────────────────────────────────────────────────────

    def action_dummy(self):
        return

    def action_reset(self):
        self.result_html = False
        self.pool_structure_json = False

    def _normalize_reservations(self, reservations, valid_team_ids, pool_count):
        """Return {team_id: pool_index} with 1-based pool indexes only."""
        out = {}
        valid = {int(i) for i in (valid_team_ids or [])}
        raw = reservations or {}
        if not isinstance(raw, dict):
            return out
        pool_count = int(pool_count or 0)
        for key, val in raw.items():
            try:
                tid = int(key)
                pidx = int(val or 0)
            except (TypeError, ValueError):
                continue
            if tid not in valid or pidx < 1 or pidx > pool_count:
                continue
            out[tid] = pidx
        return out

    def _assign_teams_to_pools(self, teams, pool_count, reservations=None):
        """Place reserved teams first, then auto-fill remaining teams.

        reservations: optional {team_id: pool_index} (1-based). Unreserved
        teams are shuffled into the currently smallest pools. If every team
        is reserved the draw is fully manual.
        """
        teams = list(teams)
        pool_count = int(pool_count or 0)
        if pool_count <= 0 or pool_count > len(teams):
            raise UserError('Invalid pool count for the selected teams.')
        team_map = {t.id: t for t in teams}
        reserved = self._normalize_reservations(
            reservations, list(team_map), pool_count,
        )
        pools = [[] for _ in range(pool_count)]
        placed = set()
        for tid, pidx in reserved.items():
            pools[pidx - 1].append(team_map[tid])
            placed.add(tid)
        rest = [t for t in teams if t.id not in placed]
        random.shuffle(rest)
        for team in rest:
            sizes = [len(p) for p in pools]
            min_size = min(sizes)
            candidates = [i for i, size in enumerate(sizes) if size == min_size]
            pools[random.choice(candidates)].append(team)
        if any(not pool for pool in pools):
            raise UserError(
                'Every pool must have at least one team. '
                'Adjust team pool preferences or the number of pools.'
            )
        return pools

    def action_generate_pools(self):
        self.ensure_one()
        teams = list(self.team_ids)
        if self.pool_count <= 0 or self.pool_count > len(teams):
            self.result_html = '<div class="alert alert-danger">Invalid pool count.</div>'
            return

        try:
            pools = self._assign_teams_to_pools(teams, self.pool_count)
        except UserError as err:
            self.result_html = '<div class="alert alert-danger">%s</div>' % err.args[0]
            return

        # Persist structure so "Apply Names" can re-render without reshuffling
        self.pool_structure_json = json.dumps([[t.id for t in pool] for pool in pools])
        # Default league matches = (teams in pool) − 1
        self.outside_pool_count = self._default_matches_per_team(pools)
        self.fixture_html = False

        # Ensure name lines are in DB (edge case: wizard opened without triggering onchange)
        if not self.pool_name_ids:
            self.write({
                'pool_name_ids': [
                    (0, 0, self._name_line_vals(i)) for i in range(1, self.pool_count + 1)
                ]
            })

        # Pre-fetch all team fields in 2 queries before entering the render loop
        self._prefetch_teams(self.team_ids)
        self.result_html = self._render_html(pools, self._get_pool_labels())

    def action_apply_names(self):
        """Re-render the pool draw with updated custom names — no reshuffling."""
        self.ensure_one()
        if not self.pool_structure_json:
            raise UserError('Generate pools first, then you can apply custom names.')

        # _load_pools now does a single batch browse + prefetch
        pools = self._load_pools()
        self.result_html = self._render_html(pools, self._get_pool_labels())

    # ── fixture generation ────────────────────────────────────────────────

    def _load_pools(self):
        """Restore pool recordsets from the saved JSON structure.
        Uses a single batch browse + prefetch so _render_html and _team_dict
        never trigger per-team DB round-trips."""
        if not self.pool_structure_json:
            raise UserError('Generate pools first before creating a fixture.')
        structure = json.loads(self.pool_structure_json)
        AuctionTeam = self.env['auction.team']

        # Single browse for all team IDs → shared prefetch context
        all_ids = [tid for pool_ids in structure for tid in pool_ids]
        all_teams = AuctionTeam.browse(all_ids)
        self._prefetch_teams(all_teams)
        team_map = {t.id: t for t in all_teams}

        return [[team_map[tid] for tid in pool_ids] for pool_ids in structure]

    def _round_robin_rounds(self, teams):
        """Circle-method round-robin: returns list of rounds (no team plays twice per round)."""
        teams = list(teams)
        if len(teams) < 2:
            return []
        if len(teams) % 2 == 1:
            teams.append(None)  # dummy bye slot
        n = len(teams)
        half = n // 2
        fixed = teams[0]
        rotating = list(teams[1:])  # length n-1
        rounds = []
        for _ in range(n - 1):
            pairs = []
            # fixed vs last rotating slot
            a, b = fixed, rotating[-1]
            if a is not None and b is not None:
                pairs.append((a, b))
            # pair the remaining n-2 slots symmetrically (indices 0..n-3)
            for i in range(half - 1):
                a, b = rotating[i], rotating[n - 3 - i]
                if a is not None and b is not None:
                    pairs.append((a, b))
            rounds.append(pairs)
            # rotate: move last element to front
            rotating = [rotating[-1]] + rotating[:-1]
        return rounds

    def _bipartite_rounds(self, pool_a, pool_b):
        """Cross-pool rounds via cyclic offset — each team gets a gap between rounds."""
        a, b = list(pool_a), list(pool_b)
        if not a or not b:
            return []
        nb = len(b)
        rounds = []
        for r in range(max(len(a), nb)):
            pairs = [(a[i], b[(i + r) % nb]) for i in range(len(a))]
            rounds.append(pairs)
        return rounds

    def _default_matches_per_team(self, pools):
        """Default league matches = (teams in pool) − 1.

        With unequal pools, use the smallest pool size − 1 so every team can
        reach that count within its own pool for Pool Round Robin.
        """
        sizes = [len(p) for p in (pools or []) if p]
        if not sizes:
            return 1
        return max(1, min(sizes) - 1)

    def _league_matches_n(self, pools):
        n = int(self.outside_pool_count or 0)
        if n < 1:
            n = self._default_matches_per_team(pools)
        return max(1, n)

    def _feasible_regular_n(self, team_count, n, max_n=None):
        """Nearest n where every team can have exactly n matches (handshaking).

        team_count * n must be even. Prefer n+1 over n-1 when the requested
        value is impossible (e.g. 3 teams × 1 match → 2).
        """
        if team_count < 2:
            return 0
        if max_n is None:
            max_n = team_count - 1
        max_n = max(0, int(max_n))
        n = max(0, min(int(n), max_n))
        if n < 1:
            return 0
        if (team_count * n) % 2 == 0:
            return n
        candidates = []
        if n + 1 <= max_n and (team_count * (n + 1)) % 2 == 0:
            candidates.append(n + 1)
        if n - 1 >= 1 and (team_count * (n - 1)) % 2 == 0:
            candidates.append(n - 1)
        if not candidates:
            return 0
        # Nearest feasible; on a tie prefer the smaller N
        return min(candidates, key=lambda x: (abs(x - n), x))

    def _circulant_regular_pairs(self, teams, n):
        """Build an exact n-regular schedule on *teams* (circulant graph).

        Every team gets exactly n matches. If the requested n is impossible
        (odd degree-sum), it is auto-adjusted to the nearest feasible value.
        Returns (pairs, effective_n).
        """
        teams = list(teams)
        random.shuffle(teams)
        s = len(teams)
        if s < 2:
            return [], 0
        n = self._feasible_regular_n(s, n, max_n=s - 1)
        if n < 1:
            return [], 0

        pairs = []
        used = set()
        # Connect each team to the next floor(n/2) neighbours on the circle
        for k in range(1, (n // 2) + 1):
            for i in range(s):
                j = (i + k) % s
                edge = (min(i, j), max(i, j))
                if edge in used:
                    continue
                used.add(edge)
                pairs.append((teams[i], teams[j]))
        # When n is odd, s is even → add opposite (diameter) edges
        if n % 2 == 1:
            half = s // 2
            for i in range(half):
                j = i + half
                pairs.append((teams[i], teams[j]))
        return pairs, n

    def _select_exact_n_matches(self, teams, candidate_pairs, n):
        """Randomly choose matches so *every* team gets exactly n games.

        Uses a configuration-style stub matching with many retries, then a
        neediest-first greedy repair. Raises UserError if impossible.
        """
        teams = list(teams)
        if not teams or n < 1:
            return []
        team_map = {t.id: t for t in teams}
        team_ids = [t.id for t in teams]

        adj = {tid: set() for tid in team_ids}
        for ta, tb in candidate_pairs:
            if ta.id in adj and tb.id in adj and ta.id != tb.id:
                adj[ta.id].add(tb.id)
                adj[tb.id].add(ta.id)

        common = min(min(int(n), len(adj[tid])) for tid in team_ids)
        common = self._feasible_regular_n(len(team_ids), common, max_n=common)
        if common < 1:
            raise UserError(
                'Cannot give every team %d matches — not enough eligible opponents '
                'for a balanced schedule. Try a different N or pool setup.' % n
            )

        def _degree_map(pairs_list):
            deg = {tid: 0 for tid in team_ids}
            for a, b in pairs_list:
                deg[a.id] += 1
                deg[b.id] += 1
            return deg

        def _from_stubs():
            """Pair random stubs; reject invalid pairings and reshuffle."""
            for _ in range(200):
                stubs = []
                for tid in team_ids:
                    stubs.extend([tid] * common)
                random.shuffle(stubs)
                used = set()
                result = []
                ok = True
                # Greedy scan with local repair
                i = 0
                while i < len(stubs) - 1:
                    a = stubs[i]
                    # find a valid partner in the remaining stubs
                    found = False
                    for j in range(i + 1, len(stubs)):
                        b = stubs[j]
                        if a == b:
                            continue
                        edge = frozenset((a, b))
                        if edge in used or b not in adj[a]:
                            continue
                        used.add(edge)
                        result.append((team_map[a], team_map[b]))
                        # swap chosen partner next to i and advance by 2
                        stubs[i + 1], stubs[j] = stubs[j], stubs[i + 1]
                        found = True
                        break
                    if not found:
                        ok = False
                        break
                    i += 2
                if ok and len(result) == (len(team_ids) * common) // 2:
                    deg = _degree_map(result)
                    if all(deg[tid] == common for tid in team_ids):
                        return result
            return None

        def _try_greedy():
            degree = {tid: 0 for tid in team_ids}
            used = set()
            result = []
            for _ in range(len(team_ids) * common):
                needing = [tid for tid in team_ids if degree[tid] < common]
                if not needing:
                    break
                random.shuffle(needing)
                needing.sort(key=lambda tid: (
                    degree[tid] - common,
                    len([
                        o for o in adj[tid]
                        if degree[o] < common and frozenset((tid, o)) not in used
                    ]),
                ))
                progress = False
                for ta in needing:
                    opps = [
                        o for o in adj[ta]
                        if degree[o] < common and frozenset((ta, o)) not in used
                    ]
                    if not opps:
                        continue
                    random.shuffle(opps)
                    opps.sort(key=lambda o: degree[o] - common)
                    tb = opps[0]
                    used.add(frozenset((ta, tb)))
                    degree[ta] += 1
                    degree[tb] += 1
                    result.append((team_map[ta], team_map[tb]))
                    progress = True
                    break
                if not progress:
                    return None
            deg = _degree_map(result)
            return result if all(deg[tid] == common for tid in team_ids) else None

        built = _from_stubs()
        if built is not None:
            return built
        for _ in range(80):
            built = _try_greedy()
            if built is not None:
                return built

        if all(len(adj[tid]) == len(team_ids) - 1 for tid in team_ids):
            pairs, _eff = self._circulant_regular_pairs(teams, common)
            return pairs

        raise UserError(
            'Could not give every team exactly %d matches with the current pools. '
            'For cross-pool fixtures, keep pools the same size, or lower N.'
            % n
        )

    def _bipartite_exact_n(self, pool_a, pool_b, n):
        """Each team plays exactly n cross matches (requires equal pool sizes)."""
        a = list(pool_a)
        b = list(pool_b)
        if not a or not b:
            return []
        if len(a) != len(b):
            raise UserError(
                'Cross-pool fixtures need equal pool sizes so every team can '
                'get the same number of matches (pools are %d and %d). '
                'Balance the pools, or use Pool Round Robin.'
                % (len(a), len(b))
            )
        random.shuffle(a)
        random.shuffle(b)
        n = min(int(n), len(b))
        if n < 1:
            return []
        pairs = []
        for r in range(n):
            for i in range(len(a)):
                pairs.append((a[i], b[(i + r) % len(b)]))
        return pairs

    def _pack_matches_into_rounds(self, pairs):
        """Greedy round packing: no team appears twice in the same round."""
        rounds = []
        busy = {}  # team_id -> set(round_index)
        for ta, tb in pairs:
            r = 0
            while True:
                if r not in busy.get(ta.id, ()) and r not in busy.get(tb.id, ()):
                    while len(rounds) <= r:
                        rounds.append([])
                    rounds[r].append((ta, tb))
                    busy.setdefault(ta.id, set()).add(r)
                    busy.setdefault(tb.id, set()).add(r)
                    break
                r += 1
        return rounds

    def _generate_matches(self, pools):
        """Return list of (team_a, team_b, group_label) based on fixture_type.

        Every team gets exactly N league matches (N = Matches per Team).
        Opponents are chosen randomly from the eligible set for the fixture type.
        """
        pool_labels = self._get_pool_labels()
        ftype = self.fixture_type
        n = self._league_matches_n(pools)
        matches = []

        if ftype == 'pool_rr':
            for pi, pool in enumerate(pools, start=1):
                label = pool_labels.get(pi, self._pool_label(pi))
                pool_teams = list(pool)
                if len(pool_teams) < 2:
                    continue
                pool_n = min(n, len(pool_teams) - 1)
                # Circulant → every team gets the same match count (auto-adjusts
                # when requested N is impossible, e.g. 3 teams × 1 → 2)
                selected, _eff_n = self._circulant_regular_pairs(pool_teams, pool_n)
                rounds = self._pack_matches_into_rounds(selected)
                for r, round_matches in enumerate(rounds):
                    for ta, tb in round_matches:
                        matches.append((ta, tb, '%s  —  Round %d' % (label, r + 1)))

        elif ftype in ('cross_pool_rr', 'custom_outside'):
            all_teams = [t for pool in pools for t in pool]
            if len(pools) < 2 or len(all_teams) < 2:
                return matches

            sizes = [len(p) for p in pools]
            outside_avail = [len(all_teams) - sz for sz in sizes]
            cross_n = min(n, min(outside_avail) if outside_avail else 0)
            if cross_n < 1:
                raise UserError(
                    'Not enough teams outside each pool to give every team '
                    '%d cross-pool matches. Reduce N or change the pools.' % n
                )

            # Two pools: cyclic construction needs equal sizes for exact N each
            if len(pools) == 2:
                selected = self._bipartite_exact_n(pools[0], pools[1], cross_n)
            else:
                if len(set(sizes)) != 1:
                    raise UserError(
                        'For cross-pool fixtures with more than 2 pools, keep '
                        'all pools the same size so every team can get exactly '
                        '%d matches. Current sizes: %s'
                        % (cross_n, ', '.join(str(s) for s in sizes))
                    )
                candidates = []
                for pi in range(len(pools)):
                    for pj in range(pi + 1, len(pools)):
                        for ta in pools[pi]:
                            for tb in pools[pj]:
                                candidates.append((ta, tb))
                selected = self._select_exact_n_matches(
                    all_teams, candidates, cross_n)

            team_pool = {}
            for pi, pool in enumerate(pools, start=1):
                for team in pool:
                    team_pool[team.id] = pi
            rounds = self._pack_matches_into_rounds(selected)
            for r, round_matches in enumerate(rounds):
                for ta, tb in round_matches:
                    pi = team_pool.get(ta.id)
                    pj = team_pool.get(tb.id)
                    if pi and pj:
                        la = pool_labels.get(pi, self._pool_label(pi))
                        lb = pool_labels.get(pj, self._pool_label(pj))
                        if pi > pj:
                            la, lb = lb, la
                        group = '%s  ×  %s  —  Round %d' % (la, lb, r + 1)
                    else:
                        group = 'Cross Pool Matches  —  Round %d' % (r + 1)
                    matches.append((ta, tb, group))

        return matches

    def _team_dict(self, team):
        b64 = None
        if team.logo:
            b64 = team.logo.decode('utf-8') if isinstance(team.logo, bytes) else team.logo
        return {
            'name': team.name,
            'logo': b64,
            'initials': ''.join(w[0].upper() for w in team.name.split()[:2]),
        }

    def action_generate_fixture(self):
        """Generate fixture schedule — embeds JSON into fixture_html for the DnD board."""
        self.ensure_one()
        pools = self._load_pools()
        matches = self._generate_matches(pools)
        if not matches:
            raise UserError(
                'No matches could be generated. '
                'Check pool size vs. outside count, or choose a different fixture type.'
            )

        # Collect tournament name + subtitle for the DnD header
        all_teams = [ta for ta, _, __ in matches] + [tb for _, tb, __ in matches]
        tournament = next(
            (t.tournament_id.name for t in all_teams if t.tournament_id), 'Fixture Schedule'
        )
        type_labels = {
            'pool_rr':        'Pool Round Robin  (N = %s)' % self.outside_pool_count,
            'cross_pool_rr':  'Cross Pool Round Robin  (N = %s)' % self.outside_pool_count,
            'custom_outside': 'Custom Cross Pool  (N = %s)' % self.outside_pool_count,
        }
        subtitle = type_labels.get(self.fixture_type, '')

        # Cache team dicts — each team can appear in many matches; avoid re-reading logos
        _team_cache = {}
        def _team_dict_cached(team):
            if team.id not in _team_cache:
                _team_cache[team.id] = self._team_dict(team)
            return _team_cache[team.id]

        matches_data = [
            {
                'group': grp,
                'section': grp.split('  —  ')[0].strip() if '  —  ' in grp else grp,
                'team_a': _team_dict_cached(ta),
                'team_b': _team_dict_cached(tb),
            }
            for ta, tb, grp in matches
        ]
        payload = json.dumps({'tournament': tournament, 'subtitle': subtitle, 'matches': matches_data})

        # Embed JSON in a hidden textarea so fixture_dnd.js can read it
        self.fixture_html = (
            f'<textarea id="fixture-data" style="display:none">{payload}</textarea>'
            f'<div style="color:#6c757d;font-size:.82rem;padding:6px 0;text-align:center;">'
            f'✅ {len(matches_data)} matches generated — drag cards below to reorder</div>'
        )

    # ── Client action JSON API ────────────────────────────────────────────

    def _client_team_payload(self, team):
        return {
            'id': team.id,
            'name': team.name or '',
            'logo_url': (
                '/web/image/auction.team/%s/logo' % team.id if team.logo else False
            ),
            'initials': ''.join(
                w[0].upper() for w in (team.name or '?').split()[:2]
            ) or '?',
            'manager': team.manager or '',
        }

    @api.model
    def _client_current_tournament(self):
        """Active tournament for Pool Generator (context wins over systray)."""
        tid = self.env.context.get('tournament_id')
        if tid:
            tournament = self.env['auction.tournament'].browse(int(tid)).exists()
            if tournament:
                return tournament
        tournament = self.env.user.tournament_id
        if not tournament:
            raise UserError('Select a tournament before using the Pool Generator.')
        return tournament

    @api.model
    def _client_build_pools(self, structure, pool_names=None):
        """Turn [[team_id, …], …] into the client pool payload."""
        if not structure:
            return [], 'Pool Draw'
        wiz = self.new({})
        name_map = {}
        for i, name in enumerate(pool_names or [], start=1):
            name_map[i] = (name or '').strip() or wiz._pool_label(i)

        all_ids = [tid for pool_ids in structure for tid in pool_ids]
        teams = self.env['auction.team'].browse(all_ids).exists()
        team_map = {t.id: t for t in teams}
        tournament_name = (
            teams[:1].tournament_id.name if teams[:1].tournament_id else 'Pool Draw'
        )
        result_pools = []
        for i, pool_ids in enumerate(structure, start=1):
            result_pools.append({
                'index': i,
                'name': name_map.get(i) or wiz._pool_label(i),
                'teams': [
                    self._client_team_payload(team_map[tid])
                    for tid in pool_ids if tid in team_map
                ],
            })
        return result_pools, tournament_name

    @api.model
    def _client_refresh_fixture(self, fixture_data):
        """Rebuild fixture match team payloads from current team records."""
        if not fixture_data:
            return False
        matches_in = fixture_data.get('matches') or []
        team_ids = set()
        for m in matches_in:
            for key in ('team_a', 'team_b'):
                team = m.get(key) or {}
                if team.get('id'):
                    team_ids.add(int(team['id']))
        team_map = {
            t.id: self._client_team_payload(t)
            for t in self.env['auction.team'].browse(list(team_ids)).exists()
        }
        matches = []
        for m in matches_in:
            ta = (m.get('team_a') or {})
            tb = (m.get('team_b') or {})
            ta_id = int(ta.get('id') or 0)
            tb_id = int(tb.get('id') or 0)
            if ta_id not in team_map or tb_id not in team_map:
                continue
            matches.append({
                'group': m.get('group') or '',
                'section': m.get('section') or '',
                'team_a': team_map[ta_id],
                'team_b': team_map[tb_id],
            })
        return {
            'tournament': fixture_data.get('tournament') or '',
            'subtitle': fixture_data.get('subtitle') or '',
            'fixture_type': fixture_data.get('fixture_type') or 'pool_rr',
            'outside_n': fixture_data.get('outside_n') or 1,
            'matches': matches,
        }

    @api.model
    def _client_tournament_filter_meta(self):
        """Tournament dropdown choices — mirrors Payment Tracker rules.

        SaaS organisers: locked to working tournament (no dropdown).
        Admins: all active tournaments.
        Other users: assigned tournament_ids (dropdown only if more than one).
        """
        user = self.env.user
        is_admin = user.has_group('auction_module.group_auction_group_admin')
        is_saas = False
        try:
            Acc = self.env['ac.saas.account']
            is_saas = bool(Acc._get_account_for_user())
        except Exception:
            is_saas = False

        if is_saas and not is_admin:
            return [], False, True, is_admin

        if is_admin:
            tournaments = self.env['auction.tournament'].sudo().search(
                [('active', '=', True)], order='name asc, id asc'
            )
        else:
            tournaments = user.sudo().tournament_ids.filtered(lambda t: t.active)
            if not tournaments and user.tournament_id:
                tournaments = user.tournament_id

        choices = [
            {'id': t.id, 'name': t.name or ('Tournament #%s' % t.id)}
            for t in tournaments
        ]
        show = bool(is_admin or len(choices) > 1)
        return choices, show, is_saas, is_admin

    @api.model
    def client_bootstrap(self, tournament_id=None):
        """Initial payload for the Pool Generator client action."""
        choices, show_filter, is_saas, is_admin = self._client_tournament_filter_meta()

        tournament = False
        if tournament_id:
            tournament = self.env['auction.tournament'].browse(int(tournament_id)).exists()
            if not tournament:
                raise UserError('Tournament not found.')
            # Non-admins may only open tournaments they are allowed to see
            if not is_admin and choices:
                allowed = {c['id'] for c in choices}
                if tournament.id not in allowed:
                    raise UserError('You do not have access to that tournament.')
        else:
            try:
                tournament = self._client_current_tournament()
            except UserError:
                tournament = self.env.user.tournament_id
            if not tournament and choices:
                tournament = self.env['auction.tournament'].browse(choices[0]['id']).exists()

        Team = self.env['auction.team']
        domain = [('tournament_id', '=', tournament.id)] if tournament else []
        teams = Team.search(domain, order='name')

        saved_pools = False
        saved_fixture = False
        default_pool_count = 2
        if tournament and tournament.pool_draw_json:
            try:
                raw = json.loads(tournament.pool_draw_json)
                structure = raw.get('structure') or []
                pool_names = raw.get('pool_names') or []
                pools, tname = self._client_build_pools(structure, pool_names)
                if pools:
                    saved_pools = {
                        'structure': structure,
                        'pools': pools,
                        'pool_names': pool_names,
                        'pool_count': raw.get('pool_count') or len(structure) or 2,
                        'team_ids': raw.get('team_ids') or [
                            tid for pool in structure for tid in pool
                        ],
                        'tournament_name': tname,
                        'reservations': raw.get('reservations') or {},
                    }
                    default_pool_count = saved_pools['pool_count']
            except (ValueError, TypeError):
                saved_pools = False

        if tournament and tournament.fixture_schedule_json:
            try:
                saved_fixture = self._client_refresh_fixture(
                    json.loads(tournament.fixture_schedule_json)
                )
                if saved_fixture and not saved_fixture.get('matches'):
                    saved_fixture = False
            except (ValueError, TypeError):
                saved_fixture = False

        return {
            'tournament': {
                'id': tournament.id if tournament else False,
                'name': tournament.name if tournament else '',
                'logo_url': (
                    '/web/image/auction.tournament/%s/logo' % tournament.id
                    if tournament and tournament.logo else False
                ),
            },
            'teams': [self._client_team_payload(t) for t in teams],
            'default_pool_count': default_pool_count,
            'saved_pools': saved_pools,
            'saved_fixture': saved_fixture,
            'tournaments': choices,
            'show_tournament_filter': show_filter,
            'is_saas': is_saas,
            'is_admin': is_admin,
            'fixture_types': [
                {'value': 'pool_rr', 'label': 'Pool Round Robin',
                 'hint': 'Random opponents within the same pool (N matches per team)'},
                {'value': 'cross_pool_rr', 'label': 'Cross Pool Round Robin',
                 'hint': 'Random opponents from other pools (N matches per team)'},
                {'value': 'custom_outside', 'label': 'Custom Outside Matches',
                 'hint': 'Same as cross-pool: each team plays N outside opponents'},
            ],
        }

    @api.model
    def client_pool_labels(self, pool_count):
        """Default Pool A / Pool B … labels for N pools."""
        wiz = self.new({'pool_count': pool_count or 2})
        count = max(1, int(pool_count or 2))
        return [
            {'index': i, 'default_label': wiz._pool_label(i), 'custom_name': wiz._pool_label(i)}
            for i in range(1, count + 1)
        ]

    @api.model
    def _resolve_publish_tournament(self, structure=None):
        """Use the teams' tournament (sudo) so projector slug always matches."""
        tournament = False
        if structure:
            flat = [tid for pool in structure for tid in (pool or [])]
            if flat:
                team = self.env['auction.team'].sudo().browse(int(flat[0])).exists()
                if team and team.tournament_id:
                    tournament = team.tournament_id
        if not tournament:
            try:
                tournament = self.with_context(
                    tournament_id=self.env.context.get('tournament_id')
                )._client_current_tournament()
            except UserError:
                tournament = self.env.user.tournament_id
        if not tournament:
            raise UserError('Select a tournament before using the Pool Generator.')
        return tournament.sudo()

    @api.model
    def _projector_reveal_until(self, seconds=5):
        from datetime import datetime, timedelta
        return datetime.utcnow() + timedelta(seconds=seconds)

    @api.model
    def _publish_pools_live(self, structure, pool_names=None, reveal_seconds=5):
        """Write pool draw to the active tournament and push it to the projector."""
        structure = [[int(tid) for tid in pool] for pool in (structure or [])]
        tournament = self._resolve_publish_tournament(structure)
        pool_names = list(pool_names or [])
        while len(pool_names) < len(structure):
            pool_names.append(self.new({})._pool_label(len(pool_names) + 1))
        pools, tournament_name = self._client_build_pools(structure, pool_names)
        if not pools:
            raise UserError('No valid teams found in this pool draw.')
        payload = {
            'structure': structure,
            'pool_names': [
                (pool_names[i] if i < len(pool_names) else None) or self.new({})._pool_label(i + 1)
                for i in range(len(structure))
            ],
            'pool_count': len(structure),
            'team_ids': [tid for pool in structure for tid in pool],
            'tournament_name': tournament_name or tournament.name or 'Pool Draw',
        }
        vals = {
            'pool_draw_json': json.dumps(payload),
            'pool_draw_user_id': self.env.uid,
            'pool_draw_datetime': fields.Datetime.now(),
            'fixture_schedule_json': False,
            'fixture_schedule_snapshot': False,
            'fixture_schedule_user_id': False,
            'fixture_schedule_datetime': False,
            'projector_board_mode': 'pools',
            'projector_board_reveal_until': (
                self._projector_reveal_until(reveal_seconds)
                if reveal_seconds and reveal_seconds > 0 else False
            ),
        }
        try:
            tournament.write(vals)
        except Exception as err:
            # Fallback if new columns are missing mid-upgrade
            raise UserError(
                'Could not publish pools to projector. Upgrade auction_module '
                'and restart Odoo, then try again. (%s)' % err
            )
        return pools, tournament_name or tournament.name, structure

    @api.model
    def _publish_fixture_live(self, structure, fixture_data, pool_names=None,
                              fixture_type='pool_rr', outside_n=1, reveal_seconds=5):
        """Write fixture + pools to tournament and push fixture board to projector."""
        structure = [[int(tid) for tid in pool] for pool in (structure or [])]
        tournament = self._resolve_publish_tournament(structure)
        pool_names = list(pool_names or [])
        while len(pool_names) < len(structure):
            pool_names.append(self.new({})._pool_label(len(pool_names) + 1))
        pools, tournament_name = self._client_build_pools(structure, pool_names)
        pool_payload = {
            'structure': structure,
            'pool_names': [
                (pool_names[i] if i < len(pool_names) else None) or self.new({})._pool_label(i + 1)
                for i in range(len(structure))
            ],
            'pool_count': len(structure),
            'team_ids': [tid for pool in structure for tid in pool],
            'tournament_name': tournament_name or tournament.name or 'Pool Draw',
        }
        matches = []
        for m in (fixture_data or {}).get('matches') or []:
            ta = m.get('team_a') or {}
            tb = m.get('team_b') or {}
            if not ta.get('id') or not tb.get('id'):
                continue
            matches.append({
                'group': m.get('group') or '',
                'section': m.get('section') or '',
                'team_a': {'id': int(ta['id'])},
                'team_b': {'id': int(tb['id'])},
            })
        if not matches:
            raise UserError('Fixture has no valid matches to publish.')
        fix_payload = {
            'tournament': (fixture_data or {}).get('tournament') or tournament.name or 'Fixture Schedule',
            'subtitle': (fixture_data or {}).get('subtitle') or '',
            'fixture_type': fixture_type or (fixture_data or {}).get('fixture_type') or 'pool_rr',
            'outside_n': int(outside_n or (fixture_data or {}).get('outside_n') or 1),
            'matches': matches,
        }
        try:
            tournament.write({
                'pool_draw_json': json.dumps(pool_payload),
                'pool_draw_user_id': self.env.uid,
                'pool_draw_datetime': fields.Datetime.now(),
                'fixture_schedule_json': json.dumps(fix_payload),
                'fixture_schedule_user_id': self.env.uid,
                'fixture_schedule_datetime': fields.Datetime.now(),
                'projector_board_mode': 'fixtures',
                'projector_board_reveal_until': (
                    self._projector_reveal_until(reveal_seconds)
                    if reveal_seconds and reveal_seconds > 0 else False
                ),
            })
        except Exception as err:
            raise UserError(
                'Could not publish fixtures to projector. Upgrade auction_module '
                'and restart Odoo, then try again. (%s)' % err
            )
        return self._client_refresh_fixture(fix_payload)

    @api.model
    def client_generate_pools(self, team_ids, pool_count, pool_names=None, reservations=None):
        """Shuffle selected teams into pools and live-publish to the projector.

        Optional ``reservations`` ({team_id: pool_index, 1-based}) force those
        teams into the chosen pool before the remaining teams are auto-filled.
        """
        team_ids = [int(t) for t in (team_ids or [])]
        pool_count = int(pool_count or 0)
        teams = list(self.env['auction.team'].browse(team_ids).exists())
        if pool_count <= 0 or pool_count > len(teams):
            raise UserError('Invalid pool count for the selected teams.')
        if len(teams) < 2:
            raise UserError('Select at least 2 teams to generate pools.')

        pools = self._assign_teams_to_pools(teams, pool_count, reservations)

        name_map = {}
        for i, name in enumerate(pool_names or [], start=1):
            name_map[i] = (name or '').strip() or self.new({})._pool_label(i)

        structure = [[t.id for t in pool] for pool in pools]
        names = [name_map.get(i) for i in range(1, pool_count + 1)]
        result_pools, tournament_name, structure = self._publish_pools_live(
            structure, names, reveal_seconds=5
        )
        return {
            'tournament_name': tournament_name,
            'structure': structure,
            'pools': result_pools,
            'published': True,
        }

    @api.model
    def client_apply_names(self, structure, pool_names=None):
        """Re-label pools without reshuffling and refresh the projector board."""
        if not structure:
            raise UserError('Generate pools first, then you can apply custom names.')
        result_pools, tournament_name, structure = self._publish_pools_live(
            structure, pool_names, reveal_seconds=0
        )
        return {
            'tournament_name': tournament_name,
            'structure': structure,
            'pools': result_pools,
            'published': True,
        }

    @api.model
    def client_clear_projector_boards(self):
        """Clear saved pools/fixtures and hide them on the projector (Pool Generator Clear)."""
        tournament = self._client_current_tournament()
        tournament.action_clear_pool_fixture_boards()
        return {
            'cleared': True,
            'tournament_id': tournament.id,
        }

    @api.model
    def client_save_pools(self, structure, pool_names=None, clear_fixture=True,
                          reservations=None):
        """Persist the current pool draw on the active tournament."""
        tournament = self._client_current_tournament()
        if not structure:
            raise UserError('Generate pools before saving.')
        structure = [[int(tid) for tid in pool] for pool in structure]
        pool_names = list(pool_names or [])
        while len(pool_names) < len(structure):
            pool_names.append(self.new({})._pool_label(len(pool_names) + 1))
        pools, tournament_name = self._client_build_pools(structure, pool_names)
        if not pools:
            raise UserError('No valid teams found in this pool draw.')
        team_ids = [tid for pool in structure for tid in pool]
        payload = {
            'structure': structure,
            'pool_names': [
                (pool_names[i] if i < len(pool_names) else None) or self.new({})._pool_label(i + 1)
                for i in range(len(structure))
            ],
            'pool_count': len(structure),
            'team_ids': team_ids,
            'tournament_name': tournament_name,
            'reservations': self._normalize_reservations(
                reservations, team_ids, len(structure),
            ),
        }
        vals = {
            'pool_draw_json': json.dumps(payload),
            'pool_draw_user_id': self.env.uid,
            'pool_draw_datetime': fields.Datetime.now(),
            'projector_board_mode': 'pools',
            'projector_board_reveal_until': False,
        }
        if clear_fixture:
            vals.update({
                'fixture_schedule_json': False,
                'fixture_schedule_snapshot': False,
                'fixture_schedule_user_id': False,
                'fixture_schedule_datetime': False,
            })
        tournament.write(vals)
        return {
            'ok': True,
            'message': 'Pool draw saved to %s' % (tournament.name or 'tournament'),
            'pools': pools,
            'structure': structure,
            'tournament_name': tournament_name,
        }

    @api.model
    def _strip_data_url(self, image_data):
        """Accept raw base64 or data:image/png;base64,... and return raw base64."""
        if not image_data:
            return False
        raw = image_data
        if isinstance(raw, bytes):
            raw = raw.decode('ascii', errors='ignore')
        raw = (raw or '').strip()
        if not raw:
            return False
        if ',' in raw and raw.lower().startswith('data:'):
            raw = raw.split(',', 1)[1]
        return raw or False

    @api.model
    def client_save_to_tournament(self, structure, pool_names=None, fixture_data=None,
                                  pool_image=None, fixture_image=None,
                                  fixture_type='pool_rr', outside_n=1,
                                  reservations=None):
        """Save pool + fixture data and both snapshot images on the tournament."""
        tournament = self._client_current_tournament()
        if not structure:
            raise UserError('Generate pools before saving.')

        # Always save pools (JSON)
        pool_res = self.client_save_pools(
            structure, pool_names,
            clear_fixture=not (fixture_data and fixture_data.get('matches')),
            reservations=reservations,
        )

        vals = {}
        pool_b64 = self._strip_data_url(pool_image)
        if pool_b64:
            vals['pool_draw_snapshot'] = pool_b64
            vals['pool_draw_user_id'] = self.env.uid
            vals['pool_draw_datetime'] = fields.Datetime.now()

        fixture_res = False
        if fixture_data and fixture_data.get('matches'):
            fixture_res = self.client_save_fixture(
                structure, fixture_data, pool_names=pool_names,
                fixture_type=fixture_type, outside_n=outside_n,
            )
            fixture_b64 = self._strip_data_url(fixture_image)
            if fixture_b64:
                vals['fixture_schedule_snapshot'] = fixture_b64
                vals['fixture_schedule_user_id'] = self.env.uid
                vals['fixture_schedule_datetime'] = fields.Datetime.now()
        else:
            vals.update({
                'fixture_schedule_snapshot': False,
                'fixture_schedule_user_id': False,
                'fixture_schedule_datetime': False,
            })

        if vals:
            tournament.write(vals)

        parts = ['Pool draw']
        if fixture_res:
            parts.append('fixture')
        if pool_b64 or (fixture_res and self._strip_data_url(fixture_image)):
            parts.append('snapshot(s)')
        return {
            'ok': True,
            'message': 'Saved %s to %s' % (
                ' + '.join(parts), tournament.name or 'tournament'
            ),
            'pools': pool_res.get('pools'),
            'structure': pool_res.get('structure'),
            'tournament_name': pool_res.get('tournament_name'),
            'fixture': (fixture_res or {}).get('fixture') if fixture_res else False,
            'has_pool_snapshot': bool(pool_b64),
            'has_fixture_snapshot': bool(
                fixture_res and self._strip_data_url(fixture_image)
            ),
        }

    @api.model
    def client_save_fixture(self, structure, fixture_data, pool_names=None,
                            fixture_type='pool_rr', outside_n=1):
        """Persist the current fixture schedule on the active tournament."""
        tournament = self._client_current_tournament()
        if not structure:
            raise UserError('Generate pools before saving a fixture.')
        if not fixture_data or not fixture_data.get('matches'):
            raise UserError('Generate a fixture before saving.')

        # Keep pools in sync without wiping the fixture we are about to save
        self.client_save_pools(structure, pool_names, clear_fixture=False)
        matches = []
        for m in fixture_data.get('matches') or []:
            ta = m.get('team_a') or {}
            tb = m.get('team_b') or {}
            if not ta.get('id') or not tb.get('id'):
                continue
            matches.append({
                'group': m.get('group') or '',
                'section': m.get('section') or '',
                'team_a': {'id': int(ta['id'])},
                'team_b': {'id': int(tb['id'])},
            })
        if not matches:
            raise UserError('Fixture has no valid matches to save.')

        payload = {
            'tournament': fixture_data.get('tournament') or tournament.name or 'Fixture Schedule',
            'subtitle': fixture_data.get('subtitle') or '',
            'fixture_type': fixture_type or fixture_data.get('fixture_type') or 'pool_rr',
            'outside_n': int(outside_n or fixture_data.get('outside_n') or 1),
            'matches': matches,
        }
        refreshed = self._client_refresh_fixture(payload)
        tournament.write({
            'fixture_schedule_json': json.dumps(payload),
            'fixture_schedule_user_id': self.env.uid,
            'fixture_schedule_datetime': fields.Datetime.now(),
            'projector_board_mode': 'fixtures',
            'projector_board_reveal_until': False,
        })
        return {
            'ok': True,
            'message': 'Fixture saved to %s' % (tournament.name or 'tournament'),
            'fixture': refreshed,
        }

    @api.model
    def client_generate_fixture(self, structure, pool_names=None,
                                fixture_type='pool_rr', outside_pool_count=1):
        """Build fixture match list for the client DnD board."""
        if not structure:
            raise UserError('Generate pools first before creating a fixture.')

        wiz = self.create({
            'team_ids': [(6, 0, [tid for pool in structure for tid in pool])],
            'selected_team_count': sum(len(p) for p in structure),
            'pool_count': len(structure),
            'pool_structure_json': json.dumps(structure),
            'fixture_type': fixture_type or 'pool_rr',
            'outside_pool_count': max(1, int(outside_pool_count or 1)),
            'pool_name_ids': [
                (0, 0, {
                    'pool_index': i,
                    'default_label': self.new({})._pool_label(i),
                    'custom_name': (
                        (pool_names[i - 1] if pool_names and i <= len(pool_names) else None)
                        or self.new({})._pool_label(i)
                    ),
                })
                for i in range(1, len(structure) + 1)
            ],
        })
        pools = wiz._load_pools()
        matches = wiz._generate_matches(pools)
        if not matches:
            raise UserError(
                'No matches could be generated. '
                'Check pool size vs. outside count, or choose a different fixture type.'
            )

        all_teams = [ta for ta, _, __ in matches] + [tb for _, tb, __ in matches]
        tournament = next(
            (t.tournament_id.name for t in all_teams if t.tournament_id),
            'Fixture Schedule',
        )
        type_labels = {
            'pool_rr': 'Pool Round Robin (N = %s)' % wiz.outside_pool_count,
            'cross_pool_rr': 'Cross Pool Round Robin (N = %s)' % wiz.outside_pool_count,
            'custom_outside': 'Custom Cross Pool (N = %s)' % wiz.outside_pool_count,
        }
        cache = {}

        def _payload(team):
            if team.id not in cache:
                cache[team.id] = self._client_team_payload(team)
            return cache[team.id]

        matches_data = [
            {
                'group': grp,
                'section': grp.split('  —  ')[0].strip() if '  —  ' in grp else grp,
                'team_a': _payload(ta),
                'team_b': _payload(tb),
            }
            for ta, tb, grp in matches
        ]
        result = {
            'tournament': tournament,
            'subtitle': type_labels.get(wiz.fixture_type, ''),
            'fixture_type': wiz.fixture_type,
            'outside_n': wiz.outside_pool_count,
            'matches': matches_data,
        }
        # Live-publish to projector (5s reveal to match console)
        try:
            self._publish_fixture_live(
                structure, result,
                pool_names=pool_names,
                fixture_type=wiz.fixture_type,
                outside_n=wiz.outside_pool_count,
                reveal_seconds=5,
            )
            result['published'] = True
        except UserError:
            result['published'] = False
        return result
