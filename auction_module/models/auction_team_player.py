# -*- coding: utf-8 -*-
import base64
import random
from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools.image import image_data_uri
import requests
import base64
import werkzeug
import werkzeug.exceptions
from urllib.parse import urlparse, parse_qs
import re
class AuctionTeamPlayer(models.Model):
    _name = 'auction.team.player'

    @api.model
    def default_get(self, fields):
        defaults = super(AuctionTeamPlayer, self).default_get(fields)
        last_record = self.search([],limit=1, order='sl_no desc')
        if last_record:
            defaults.update({'sl_no': last_record.sl_no+1})
        else:
            defaults.update({'sl_no': 1})
        return defaults

    sl_no = fields.Integer("Sl No")
    name = fields.Char(string="Name of the player", required=True)
    contact = fields.Char("Mobile Number")
    address = fields.Text("Address")
    batting_style = fields.Char(string="Batting Style", required=True, default='Right Handed Batter')
    bowling_style = fields.Char(string="Bowling Style", required=True, default='Right Arm')
    role = fields.Char()
    player_type = fields.Selection([('icon', 'Icon'), ('domestic', 'Domestic'), ('foreign', 'Foreign')], default='domestic')
    photo = fields.Binary("Photo")
    photo_url = fields.Char("Photo URL")
    payment_url = fields.Char("Payment URL")
    state = fields.Selection([('draft', 'Draft'), ('auction', 'In Auction'), ('sold', 'Sold'), ('unsold', 'Unsold')], default='draft')
    amount_paid = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')
    tournament_type = fields.Selection(related='tournament_id.tournament_type')
    assigned_team_id = fields.Many2one('auction.team', 'Team')
    icon_player = fields.Boolean("Key Player")
    notes = fields.Char()
    #other details
    current_team = fields.Char("Current Team")
    jersy_size = fields.Char('Jersy Size')
    jersy_number = fields.Char("Number in Jersy")
    jersy_name = fields.Char("Name in Jersy")
    blood_group = fields.Char("Blood Group")

    def print_player_cards(self):
        return self.env.ref('auction_module.action_report_player_card').report_action(self)

    # def print_player_card(self):
    #     players = self.search([])
    #     return self.env.ref('auction_module.action_player_card_auction').report_action(players.ids)

    @api.model
    def action_player_card_report(self):
        report_data = {
                'type': 'ir.actions.report',
                'report_name': 'auction_module.player_card_template',
                'report_type': 'qweb-pdf',
                'data': {'model': 'auction.team.player'},

        }
        return report_data

    @api.model
    def _get_report_values(self, docids, data=None):
        docs = self.browse(docids)
        print(f"Report docs: {docs}")  # Debugging statement
        return {
            'doc_ids': docids,
            'doc_model': 'your.model',
            'docs': docs,
            'tournament': self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        }
    def get_base64_from_url(self,image_url):
        try:
            # Download the image
            response = requests.get(image_url)
            response.raise_for_status()  # Ensure we notice bad responses

            # Encode the image content in base64
            image_base64 = base64.b64encode(response.content).decode('utf-8')

            return image_base64

        except requests.exceptions.RequestException as e:
            # Handle any errors that occur during the download
            return None


    def get_image_base64_from_google_url(self, url):
        """
        Converts a Google Drive 'open?id=' URL into a direct download URL
        and returns Base64 encoded binary.
        """

        try:
            if not url:
                return False

            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            file_id = query.get("id", [None])[0]

            if not file_id:
                return False

            # Convert to direct download URL
            download_url = f"https://drive.google.com/uc?export=download&id={file_id}"

            # Download the file
            response = requests.get(download_url, allow_redirects=True, timeout=20)
            response.raise_for_status()

            # Must be an image
            if "image" not in response.headers.get("Content-Type", ""):
                print("Not an image, Google returned:", response.headers.get("Content-Type"))
                return False

            return base64.b64encode(response.content)

        except Exception as e:
            print("Google Drive image fetch error:", e)
            return False


    @api.model
    def create(self, vals):
        tournament_id = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        if tournament_id:
            vals.update({'tournament_id': tournament_id.id})
        if 'Icon' in  vals.get('player_type', False):
            vals.update({'player_type': 'icon'})
        if vals.get('photo_url', False):
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
               vals.update({'photo': image_base64})

        if not vals.get('payment_url', False):
            vals.update({'amount_paid': False})
        print(vals, "ssssss")
        player = super(AuctionTeamPlayer, self).create(vals)
        return player

    def write(self, vals):
        if 'photo_url' in vals:
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
                vals.update({'photo': image_base64})
        res = super(AuctionTeamPlayer, self).write(vals)
        return res

    def get_icon_players(self, team_id):
        players_domain = [('icon_player', '=', True), ('assigned_team_id', '=', team_id)]
        players = self.search(players_domain, order='sl_no asc')
        return players

    def get_auction_players(self):
        players_domain = [('icon_player', '=', False),('state', '=', 'auction')]
        players = self.search(players_domain, order='sl_no asc')
        return players

    def get_random_player(self):
        tournament_id = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        random_player = False
        # icon_players = self.env['auction.team'].search([]).mapped('key_player_ids')
        # players_domain = [('state', '=', 'auction')]
        # if icon_players:
        #     players_domain.append(('id', 'not in', icon_players.ids))

        players = self.get_auction_players()
        if players:
            player_ids = players.ids
            if tournament_id.player_appearance_algorithm == 'random':

                random_player_id = random.choice(player_ids)
                random_player = self.browse(random_player_id)
            else:
                random_player = self.browse(player_ids[0])
        return random_player

    def action_unsold(self):
        for player in self:
            if player.state == 'auction':
                player.state = 'unsold'
                message = player.name + ' is Unsold!'
                player.create_unsold_auction_history( message, tournament_id=player.tournament_id.id,
                                              player=player)
                self.env.user.notify_success(message)

    def action_auction(self):
        context = self.env.context.copy()
        for player in self:
            if player.state == 'unsold':
                player.state = 'auction'
                if not context.get('mass_update', False):
                    message = player.name + ' brought to auction successfully!'
                    self.env.user.notify_success(message)
        if context.get('mass_update', False):
            message = 'Selected players brought to auction successfully!'
            self.env.user.notify_success(message)

    def action_revoke_key_player(self):
        for player in self:
            if player.icon_player:
                team_id = player.assigned_team_id
                player.write({
                    'assigned_team_id': False,
                    'state': 'auction',
                    'icon_player': False,

                })
                team_id.key_player_ids = [(3, player.id)]
                message = player.name + 'has been revoked from icon player list and brought to auction successfully!'
                self.env.user.notify_success(message)

    def button_sell_player(self, player_id, other_data):
        team_id = self.env['auction.team'].browse(int(team_id))
        player = self.env['auction.team.player'].browse(int(player_id))
        auction = self.env['auction.auction'].search([('team_id', '=', int(team_id))])
        auction_line_data = {
            'player_id': player.id,
            'points': points,

        }
        message = player.name + ' sold to the '+ auction.team_id.name+' for ' + str(points) + ' points successfully!'

        auction.player_ids = [(0, 0, auction_line_data)]
        player.assigned_team_id = auction.team_id and auction.team_id.id or False
        player.state = 'sold'
        self.create_auction_history(team_id.id, message, tournament_id=player.tournament_id.id, player=player)
        self.env.user.notify_success(message)

    def create_auction_history(self, team_id, message, tournament_id, player):
        self.env['auction.history'].create(
            {
                'team_id': team_id,
                'message': message,
                'tournament_id': tournament_id,
                'player_photo': player.photo
            }
        )

    def create_unsold_auction_history(self, message, tournament_id, player):
        self.env['auction.history'].create(
            {
                'message': message,
                'tournament_id': tournament_id,
                'player_photo': player.photo
            }
        )
