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
from twilio.rest import Client

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
    batting_style = fields.Char(string="Batting Style", required=True)
    bowling_style = fields.Char(string="Bowling Style", required=True)
    role = fields.Char()

    photo = fields.Binary("Photo")
    photo_url = fields.Char("Photo URL")
    payment_url = fields.Char("Payment URL")
    state = fields.Selection([('draft', 'Draft'), ('auction', 'In Auction'), ('sold', 'Sold'), ('unsold', 'Unsold')], default='draft')
    amount_paid = fields.Boolean(default=True)
    active = fields.Boolean(default=True)
    tournament_id = fields.Many2one('auction.tournament', 'Tournament')
    assigned_team_id = fields.Many2one('auction.team', 'Team')
    icon_player = fields.Boolean("Key Player")
    notes = fields.Char()

    # def action_send_whatsapp(self):
    #     account_sid = 'ACe03cfa5fad6b7c9e71a01c6347536cdf'  # Replace with your Twilio Account SID
    #     auth_token = 'd125e462e6e15690dab9a4b7e6b38b23'  # Replace with your Twilio Auth Token
    #     group_id = 'H72h0IsRWldBDFgmKzwzmU'
    #     # access_token = 'd125e462e6e15690dab9a4b7e6b38b23'
    #     client = Client(account_sid, auth_token)
    #     group_id = 'whatsapp:+919746355169'
    #     from_whatsapp_number = 'whatsapp:+14155238886'
    #     message_body = 'Priyan sold to Hunters for 2300.'
    #     message = client.messages.create(
    #         from_=from_whatsapp_number,
    #         body=message_body,
    #         to=group_id
    #     )
    #
    #     print(f"Message sent successfully with SID: {message.sid}")
    # @api.model
    # def send_whatsapp_message(self, group_id, message, attachment_url=None):
    #     # WhatsApp API Credentials
    #     access_token = 'YOUR_ACCESS_TOKEN'  # Get from Meta for Developers
    #     phone_number_id = 'YOUR_PHONE_NUMBER_ID'  # WhatsApp Business Number ID
    #     api_url = f'https://graph.facebook.com/v16.0/{phone_number_id}/messages'
    #
    #     headers = {
    #         'Authorization': f'Bearer {access_token}',
    #         'Content-Type': 'application/json',
    #     }
    #
    #     # Message Data
    #     data = {
    #         "messaging_product": "whatsapp",
    #         "to": group_id,  # Use the group's WhatsApp number or ID
    #         "type": "text",
    #         "text": {"body": message},
    #     }
    #
    #     # If attachment is provided
    #     if attachment_url:
    #         # Upload media first
    #         upload_url = f"https://graph.facebook.com/v16.0/{phone_number_id}/media"
    #         media_data = {
    #             "messaging_product": "whatsapp",
    #             "type": "document",
    #             "url": attachment_url,  # URL of your document
    #         }
    #         response = requests.post(upload_url, headers=headers, json=media_data)
    #         response_data = response.json()
    #
    #         if 'id' in response_data:
    #             media_id = response_data['id']
    #             # Modify message data to send the attachment
    #             data = {
    #                 "messaging_product": "whatsapp",
    #                 "to": group_id,
    #                 "type": "document",
    #                 "document": {
    #                     "id": media_id,
    #                     "caption": "Here is the attachment",
    #                 },
    #             }
    #         else:
    #             raise Exception(f"Media upload failed: {response_data.get('error', {})}")
    #
    #     # Send Message
    #     response = requests.post(api_url, headers=headers, json=data)
    #     if response.status_code == 200:
    #         return True
    #     else:
    #         raise Exception(f"Failed to send WhatsApp message: {response.json()}")

    def print_player_card(self):
        players = self.search([])
        return self.env.ref('auction_module.action_player_card_auction').report_action(players.ids)

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

    @api.model
    def create(self, vals):
        tournament_id = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        if tournament_id:
            vals.update({'tournament_id': tournament_id.id})
        if vals.get('photo_url', False):
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
               vals.update({'photo': image_base64})
        if not vals.get('payment_url', False):
            vals.update({'amount_paid': False})
        player = super(AuctionTeamPlayer, self).create(vals)
        return player

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
        for player in self:
            if player.state == 'unsold':
                player.state = 'auction'
                message = player.name + ' brought to auction successfully!'
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
