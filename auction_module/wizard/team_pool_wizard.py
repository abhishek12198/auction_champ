# models/team_pool_wizard.py
from odoo import models, fields, api
import random
from math import ceil

class TeamPoolWizard(models.TransientModel):
    _name = 'auction.team.pool.wizard'
    _description = 'Team Pool Generator'

    team_ids = fields.Many2many(
        'auction.team',
        string='Select Teams',
        required=True
    )
    selected_team_count = fields.Integer(
        string='No of Teams Selected',
        required=True,
    )
    pool_count = fields.Integer(
        string='Number of Pools',
        required=True,
        default=2
    )

    result_html = fields.Html(
        string='Pool Result',
        readonly=True,
        sanitize=False,
    )

    @api.onchange('team_ids')
    def onchange_team_ids(self):
        if self.team_ids:
            self.selected_team_count = len(self.team_ids)

    def action_dummy(self):
        return

    def action_reset(self):
        self.result_html = False

    def action_generate_pools(self):
        self.ensure_one()

        teams = list(self.team_ids)
        total_teams = len(teams)

        if self.pool_count <= 0 or self.pool_count > total_teams:
            self.result_html = """
                <div class="alert alert-danger">
                    Invalid pool count.
                </div>
            """
            return

        import random
        import base64
        random.shuffle(teams)

        pools = [[] for _ in range(self.pool_count)]

        for index, team in enumerate(teams):
            pools[index % self.pool_count].append(team)

        pool_header_colors = ['#1565C0','#B71C1C','#2E7D32','#6A1B9A','#E65100','#006064','#880E4F','#37474F']

        tournament_name = teams[0].tournament_id.name if teams and teams[0].tournament_id else 'Pool Draw'
        max_teams = max(len(p) for p in pools)
        col_width = f'{100 // self.pool_count}%'

        # ── shared styles ──────────────────────────────────────────────
        wrap_s   = 'background:#0d0d2b;padding:32px 28px 36px;border-radius:16px;font-family:Segoe UI,Arial,sans-serif;display:block;width:100%;box-sizing:border-box;'
        title_s  = 'display:block;text-align:center;color:#FFD54F;font-size:1.4rem;font-weight:800;letter-spacing:6px;text-transform:uppercase;margin-bottom:6px;'
        divider_s= 'display:block;width:80px;height:4px;background:#FFD54F;margin:0 auto 20px;border-radius:2px;'
        grid_s   = 'display:flex;width:100%;'

        def hdr_cell(color):
            return (f'display:block;flex:1;background:{color};color:#FFD54F;'
                    f'text-align:center;font-size:1rem;font-weight:800;letter-spacing:3px;'
                    f'padding:12px 8px;border-right:3px solid #0d0d2b;box-sizing:border-box;')

        def data_cell():
            return ('display:block;flex:1;padding:9px 12px;'
                    'border-right:1px solid rgba(255,255,255,0.1);'
                    'border-bottom:1px solid rgba(255,255,255,0.1);'
                    'background:rgba(255,255,255,0.05);box-sizing:border-box;')

        def empty_cell():
            return ('display:block;flex:1;padding:9px 12px;'
                    'border-right:1px solid rgba(255,255,255,0.06);'
                    'border-bottom:1px solid rgba(255,255,255,0.06);'
                    'background:rgba(255,255,255,0.02);box-sizing:border-box;')

        # ── header row ─────────────────────────────────────────────────
        header_cells = ''
        for i, pool in enumerate(pools, start=1):
            label = chr(64 + i)
            color = pool_header_colors[(i - 1) % len(pool_header_colors)]
            header_cells += f'<div style="{hdr_cell(color)}">POOL {label}</div>'

        # ── team rows ──────────────────────────────────────────────────
        team_rows = ''
        for row in range(max_teams):
            cells = ''
            for pool in pools:
                if row < len(pool):
                    team = pool[row]
                    if team.logo:
                        logo_b64 = team.logo.decode('utf-8') if isinstance(team.logo, bytes) else team.logo
                        img = (f'<img src="data:image/png;base64,{logo_b64}" '
                               f'style="height:20px;width:20px;object-fit:contain;border-radius:3px;'
                               f'margin-right:8px;display:inline-block;vertical-align:middle;"/>')
                    else:
                        initials = ''.join(w[0].upper() for w in team.name.split()[:2])
                        img = (f'<span style="display:inline-block;height:20px;width:20px;'
                               f'background:#ffffff30;border-radius:3px;font-size:8px;font-weight:800;'
                               f'color:#fff;margin-right:8px;vertical-align:middle;'
                               f'text-align:center;line-height:20px;">{initials}</span>')
                    name = f'<span style="color:#ffffff;font-size:0.95rem;font-weight:600;vertical-align:middle;">{team.name}</span>'
                    cells += f'<div style="{data_cell()}">{img}{name}</div>'
                else:
                    cells += f'<div style="{empty_cell()}"></div>'
            team_rows += f'<div style="{grid_s}">{cells}</div>'

        html = (
            f'<div style="{wrap_s}">'
            f'<div style="{title_s}">{tournament_name}</div>'
            f'<div style="{divider_s}"></div>'
            f'<div style="{grid_s}">{header_cells}</div>'
            f'{team_rows}'
            f'</div>'
        )

        self.result_html = html


