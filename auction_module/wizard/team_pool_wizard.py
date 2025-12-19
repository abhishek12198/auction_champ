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

    pool_count = fields.Integer(
        string='Number of Pools',
        required=True,
        default=2
    )

    result_html = fields.Html(
        string='Pool Result',
        readonly=True
    )

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
        random.shuffle(teams)

        pools = [[] for _ in range(self.pool_count)]

        for index, team in enumerate(teams):
            pools[index % self.pool_count].append(team)

        html = """
        <div class="row g-3">
        """

        for i, pool in enumerate(pools, start=1):
            pool_label = chr(64 + i)  # A, B, C...

            html += f"""
            <div class="col-lg-3 col-md-4 col-sm-6">
                <div class="card shadow-sm h-100">
                    <div class="card-header bg-primary text-white text-center">
                        <strong>Pool {pool_label}</strong><br/>
                        <small>({len(pool)} Teams)</small>
                    </div>
                    <table class="table table-sm table-bordered mb-0">
                        <tbody>
            """

            for team in pool:
                html += f"""
                    <tr>
                        <td class="fw-bold text-center">
                            {team.name}
                        </td>
                    </tr>
                """

            html += """
                        </tbody>
                    </table>
                </div>
            </div>
            """

        html += "</div>"

        self.result_html = html


