# -*- coding: utf-8 -*-
import base64

from odoo import api, models, fields, _
from odoo.exceptions import UserError, ValidationError

import werkzeug
import werkzeug.exceptions


class ViewTeamDetails(models.TransientModel):
    _name = 'auction.view.team.details'

    html_field = fields.Html()
    team_id = fields.Many2one('auction.team', 'Team')
    team_logo = fields.Binary(related='team_id.logo')
    remaining_points = fields.Integer(string="Remaining points")
    remaining_players_count = fields.Integer(string="Remaining players required")
    suggestion = fields.Html()

    @api.model
    def default_get(self, fields):
        defaults = super(ViewTeamDetails, self).default_get(fields)
        if self.env.context.get('active_id', False):
            auction = self.env['auction.auction'].browse(self.env.context.get('active_id', False))
            if auction:

                defaults.update({'team_id': auction.team_id.id, 'remaining_points': auction.remaining_points,
                                 'remaining_players_count': auction.remaining_players_count, 'html_field': self.generate_player_table(auction),
                                 'suggestion': self.generate_suggestion(auction)})
        return defaults
    def generate_player_table(self, auction):
        table_html = ''
        if auction.player_ids:

            table_html = """
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr>
                            <th style="border: 1px solid black; padding: 8px;">Name</th>
                            <th style="border: 1px solid black; padding: 8px;">Contact</th>
                            <th style="border: 1px solid black; padding: 8px;">Points</th>
                            <th style="border: 1px solid black; padding: 8px;">Role</th>
                        </tr>
                    </thead>
                    <tbody>
                """
            for record in auction.player_ids:
                table_html += f"""
                        <tr>
                            <td style="border: 1px solid black; padding: 8px;">{record.player_id.name}</td>
                            <td style="border: 1px solid black; padding: 8px;">{record.contact}</td>
                            <td style="border: 1px solid black; padding: 8px;">{record.points}</td>
                            <td style="border: 1px solid black; padding: 8px;">{record.player_id.role}</td>
                            
                        </tr>
                    """
            table_html += """
                    </tbody>
                </table>
                """
            return table_html

    def generate_suggestion(self, auction):
        suggestion_html = ""
        if auction.max_limited == 'yes':
            suggestion_html = f"""
                        <strong><p style="color: blue; text-align: right;">One player can go maximum points upto {auction.max_points}</p></strong>
                    """
        else:
            remaining_players = auction.remaining_players_count - 1
            base_point = auction.base_point
            max_points_for_next_player = auction.remaining_points - (remaining_players * base_point)
            suggestion_html = f"""
                            <strong><p style="color: blue; text-align: right;">One player can go maximum points upto {max_points_for_next_player}</p></strong>
                            <strong><p style="color: blue; text-align: right;">Remaining players you can bid for base points  {base_point}</p></strong>
                        """
        return suggestion_html

    def button_print_players_list(self):
        active_id = self.env.context.get('active_id', False)
        auction = self.env['auction.auction'].browse(active_id)
        return self.env.ref('auction_module.action_report_auction_players').report_action(auction)
