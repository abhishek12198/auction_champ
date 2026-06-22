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
        ('cross_pool_rr', 'Cross Pool Round Robin (all teams vs other pools)'),
        ('custom_outside','Custom Outside Pool Count (each team plays N teams outside pool)'),
    ], string='Fixture Type', default='pool_rr')
    outside_pool_count = fields.Integer(string='Outside Pool Matches per Team (N)', default=1)
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

    def action_generate_pools(self):
        self.ensure_one()
        teams = list(self.team_ids)
        if self.pool_count <= 0 or self.pool_count > len(teams):
            self.result_html = '<div class="alert alert-danger">Invalid pool count.</div>'
            return

        random.shuffle(teams)
        pools = [[] for _ in range(self.pool_count)]
        for i, team in enumerate(teams):
            pools[i % self.pool_count].append(team)

        # Persist structure so "Apply Names" can re-render without reshuffling
        self.pool_structure_json = json.dumps([[t.id for t in pool] for pool in pools])

        # Ensure name lines are in DB (edge case: wizard opened without triggering onchange)
        if not self.pool_name_ids:
            self.write({
                'pool_name_ids': [
                    (0, 0, self._name_line_vals(i)) for i in range(1, self.pool_count + 1)
                ]
            })

        self.result_html = self._render_html(pools, self._get_pool_labels())

    def action_apply_names(self):
        """Re-render the pool draw with updated custom names — no reshuffling."""
        self.ensure_one()
        if not self.pool_structure_json:
            raise UserError('Generate pools first, then you can apply custom names.')

        structure = json.loads(self.pool_structure_json)
        AuctionTeam = self.env['auction.team']
        pools = [[AuctionTeam.browse(tid) for tid in pool_ids] for pool_ids in structure]

        self.result_html = self._render_html(pools, self._get_pool_labels())

    # ── fixture generation ────────────────────────────────────────────────

    def _load_pools(self):
        """Restore pool recordsets from the saved JSON structure."""
        if not self.pool_structure_json:
            raise UserError('Generate pools first before creating a fixture.')
        structure = json.loads(self.pool_structure_json)
        AuctionTeam = self.env['auction.team']
        return [[AuctionTeam.browse(tid) for tid in pool_ids] for pool_ids in structure]

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

    def _generate_matches(self, pools):
        """Return list of (team_a, team_b, group_label) based on fixture_type.
        Rounds are interleaved so no team plays consecutive matches."""
        pool_labels = self._get_pool_labels()
        ftype = self.fixture_type
        matches = []

        if ftype == 'pool_rr':
            # Generate rounds per pool, then list each pool fully before the next
            for pi, pool in enumerate(pools, start=1):
                label = pool_labels.get(pi, self._pool_label(pi))
                rounds = self._round_robin_rounds(list(pool))
                for r, round_matches in enumerate(rounds):
                    for ta, tb in round_matches:
                        matches.append((ta, tb, f'{label}  —  Round {r + 1}'))

        elif ftype == 'cross_pool_rr':
            pool_pair_rounds = []
            for pi in range(len(pools)):
                for pj in range(pi + 1, len(pools)):
                    la = pool_labels.get(pi + 1, self._pool_label(pi + 1))
                    lb = pool_labels.get(pj + 1, self._pool_label(pj + 1))
                    label = f'{la}  ×  {lb}'
                    rounds = self._bipartite_rounds(pools[pi], pools[pj])
                    pool_pair_rounds.append((label, rounds))

            max_r = max((len(r) for _, r in pool_pair_rounds), default=0)
            for r in range(max_r):
                for label, rounds in pool_pair_rounds:
                    if r < len(rounds):
                        for ta, tb in rounds[r]:
                            matches.append((ta, tb, f'{label}  —  Round {r + 1}'))

        elif ftype == 'custom_outside':
            n = max(1, self.outside_pool_count or 1)
            all_cross = []
            for pi in range(len(pools)):
                for pj in range(pi + 1, len(pools)):
                    for ta in pools[pi]:
                        for tb in pools[pj]:
                            all_cross.append((ta, tb))
            random.shuffle(all_cross)

            match_count = {}
            for ta, tb in all_cross:
                if match_count.get(ta.id, 0) < n and match_count.get(tb.id, 0) < n:
                    matches.append((ta, tb, 'Cross Pool Matches'))
                    match_count[ta.id] = match_count.get(ta.id, 0) + 1
                    match_count[tb.id] = match_count.get(tb.id, 0) + 1

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
            'pool_rr':        'Pool Round Robin',
            'cross_pool_rr':  'Cross Pool Round Robin',
            'custom_outside': f'Custom Cross Pool  (N = {self.outside_pool_count})',
        }
        subtitle = type_labels.get(self.fixture_type, '')

        matches_data = [
            {
                'group': grp,
                'section': grp.split('  —  ')[0].strip() if '  —  ' in grp else grp,
                'team_a': self._team_dict(ta),
                'team_b': self._team_dict(tb),
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
