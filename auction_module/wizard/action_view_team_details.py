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
        navy    = '#0F2447'
        gold    = '#E8A020'
        lb      = '#EBF3FF'
        border  = '#C8D8F0'
        alt_row = '#F4F8FF'
        muted   = '#7A8DA8'

        spent     = auction.total_point - auction.remaining_points
        recruited = auction.max_players - auction.remaining_players_count

        # ── Masthead ──────────────────────────────────────────────────────
        logo_html = ''
        if auction.team_id.logo:
            logo_b64 = auction.team_id.logo.decode('utf-8') if isinstance(auction.team_id.logo, bytes) else auction.team_id.logo
            logo_html = (f'<img src="data:image/png;base64,{logo_b64}" '
                         f'style="height:60px;width:60px;object-fit:contain;'
                         f'border-radius:6px;border:2px solid {gold};background:#fff;"/>')

        html = f"""
<div style="font-family:Arial,Helvetica,sans-serif;color:#1A1A2E;
            border:1px solid {border};overflow:hidden;">

  <div style="background-color:{navy};padding:14px 16px;border-bottom:3px solid {gold};
              display:flex;align-items:center;gap:14px;">
    {logo_html}
    <div>
      <div style="color:#FFFFFF;font-size:16px;font-weight:bold;
                  letter-spacing:1px;text-transform:uppercase;">
        {auction.team_id.name}
      </div>
      <div style="color:#A8C0E0;font-size:11px;margin-top:3px;">
        {auction.tournament_id.name} &nbsp;|&nbsp; Owner: {auction.manager or '&#8212;'}
      </div>
      <div style="color:{gold};font-size:11px;font-weight:bold;
                  letter-spacing:2px;margin-top:6px;text-transform:uppercase;">
        Team Squad Summary
      </div>
    </div>
  </div>

  <!-- Stats bar -->
  <table style="width:100%;border-collapse:collapse;background-color:{lb};">
    <tr>
      <td style="padding:8px 12px;border-right:1px solid {border};
                 border-bottom:1px solid {border};text-align:center;">
        <div style="font-size:8px;color:{muted};text-transform:uppercase;
                    letter-spacing:1px;">Total Budget</div>
        <div style="font-size:16px;font-weight:bold;color:{navy};">
          {auction.total_point}
        </div>
      </td>
      <td style="padding:8px 12px;border-right:1px solid {border};
                 border-bottom:1px solid {border};text-align:center;">
        <div style="font-size:8px;color:{muted};text-transform:uppercase;
                    letter-spacing:1px;">Spent</div>
        <div style="font-size:16px;font-weight:bold;color:#C0392B;">
          {spent}
        </div>
      </td>
      <td style="padding:8px 12px;border-right:1px solid {border};
                 border-bottom:1px solid {border};text-align:center;">
        <div style="font-size:8px;color:{muted};text-transform:uppercase;
                    letter-spacing:1px;">Remaining</div>
        <div style="font-size:16px;font-weight:bold;color:#27AE60;">
          {auction.remaining_points}
        </div>
      </td>
      <td style="padding:8px 12px;border-right:1px solid {border};
                 border-bottom:1px solid {border};text-align:center;">
        <div style="font-size:8px;color:{muted};text-transform:uppercase;
                    letter-spacing:1px;">Players</div>
        <div style="font-size:16px;font-weight:bold;color:{navy};">
          {recruited} / {auction.max_players}
        </div>
      </td>
      <td style="padding:8px 12px;border-bottom:1px solid {border};text-align:center;">
        <div style="font-size:8px;color:{muted};text-transform:uppercase;
                    letter-spacing:1px;">Max Next Bid</div>
        <div style="font-size:16px;font-weight:bold;color:{gold};">
          {auction.max_call}
        </div>
      </td>
    </tr>
  </table>
"""
        # ── Player rows ───────────────────────────────────────────────────
        if auction.player_ids:
            html += f"""
  <table style="width:100%;border-collapse:collapse;">
    <thead>
      <tr style="background-color:#1A3A6A;">
        <th style="color:#FFFFFF;padding:8px 6px;font-size:10px;text-transform:uppercase;
                   letter-spacing:1px;border:1px solid {navy};text-align:center;width:30px;">#</th>
        <th style="color:#FFFFFF;padding:8px;font-size:10px;text-transform:uppercase;
                   letter-spacing:1px;border:1px solid {navy};text-align:left;">Player</th>
        <th style="color:#FFFFFF;padding:8px;font-size:10px;text-transform:uppercase;
                   letter-spacing:1px;border:1px solid {navy};text-align:center;">Tier</th>
        <th style="color:#FFFFFF;padding:8px;font-size:10px;text-transform:uppercase;
                   letter-spacing:1px;border:1px solid {navy};text-align:center;">Role</th>
        <th style="color:#FFFFFF;padding:8px;font-size:10px;text-transform:uppercase;
                   letter-spacing:1px;border:1px solid {navy};text-align:left;">Mobile</th>
        <th style="color:#FFFFFF;padding:8px;font-size:10px;text-transform:uppercase;
                   letter-spacing:1px;border:1px solid {navy};text-align:center;">Points</th>
      </tr>
    </thead>
    <tbody>
"""
            for i, p in enumerate(auction.player_ids):
                row_bg     = alt_row if i % 2 == 0 else '#FFFFFF'
                tier_color = p.tier_color or '#3498db'
                tier_name  = p.player_id.tier_id.name if p.player_id.tier_id else ''
                dot = (f'<span style="display:inline-block;width:8px;height:8px;'
                       f'background-color:{tier_color};border-radius:50%;'
                       f'margin-right:4px;vertical-align:middle;"></span>')
                html += f"""
      <tr style="background-color:{row_bg};">
        <td style="padding:7px 6px;border:1px solid {border};text-align:center;
                   font-size:11px;color:{muted};">{p.player_id.sl_no}</td>
        <td style="padding:7px 8px;border:1px solid {border};font-size:12px;
                   font-weight:bold;color:{navy};text-transform:uppercase;">
          {p.player_id.name}
        </td>
        <td style="padding:7px 8px;border:1px solid {border};text-align:center;
                   font-size:10px;">{dot}{tier_name}</td>
        <td style="padding:7px 8px;border:1px solid {border};text-align:center;
                   font-size:10px;color:#5A6A7E;text-transform:uppercase;
                   letter-spacing:1px;">{p.player_id.role or '&#8212;'}</td>
        <td style="padding:7px 8px;border:1px solid {border};font-size:11px;
                   color:#3A4A5E;">{p.contact or '&#8212;'}</td>
        <td style="padding:7px 8px;border:1px solid {border};text-align:center;
                   font-size:13px;font-weight:bold;color:{navy};">{p.points}</td>
      </tr>
"""
            html += "    </tbody>\n  </table>\n"
        else:
            html += f"""
  <div style="padding:28px;text-align:center;background-color:#FAFCFF;
              border-top:1px solid {border};">
    <div style="color:{muted};font-size:13px;font-style:italic;">
      No players recruited yet.
    </div>
  </div>
"""

        # ── Hint strip ────────────────────────────────────────────────────
        if auction.remaining_players_count > 0:
            if auction.max_limited == 'yes':
                hint = (f"Maximum bid for any player: "
                        f"<strong>{auction.max_points}</strong> pts")
            else:
                hint = (f"Max bid for next player: "
                        f"<strong>{auction.max_call}</strong> pts "
                        f"&nbsp;|&nbsp; "
                        f"Remaining {auction.remaining_players_count - 1} slot(s) "
                        f"fillable at base: "
                        f"<strong>{auction.base_point}</strong> pts each")
            html += f"""
  <div style="padding:8px 14px;background-color:#F0F6FF;
              border-top:2px solid {gold};font-size:11px;color:#3A4A5E;">
    <span style="color:{gold};font-weight:bold;margin-right:6px;">&#9432;</span>
    {hint}
  </div>
"""

        html += "</div>"
        return html

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

    def button_print_roster(self):
        active_id = self.env.context.get('active_id', False)
        auction = self.env['auction.auction'].browse(active_id)
        return self.env.ref('auction_module.action_report_auction_players').report_action(auction)

    def button_print_team_template(self):
        active_id = self.env.context.get('active_id', False)
        auction = self.env['auction.auction'].browse(active_id)
        return self.env.ref('auction_module.action_report_auction_template').report_action(auction)

    def button_print_squad_poster(self):
        active_id = self.env.context.get('active_id', False)
        return {
            'type': 'ir.actions.act_url',
            'url': '/auction/squad-poster/%d' % active_id,
            'target': 'new',
        }
