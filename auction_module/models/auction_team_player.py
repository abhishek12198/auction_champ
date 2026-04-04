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
    is_on_stage = fields.Boolean("Currently on Stage", default=False,
                                  help="True when this player is actively displayed in the auction stage. Only one player should have this True at a time.")
    tier_id = fields.Many2one('auction.player.tier', string='Tier')
    previous_tier_id = fields.Many2one('auction.player.tier', string='Previous Tier', help='Stores the tier before the player was promoted to Icon Player, used to restore on revoke.')
    tier_color = fields.Selection(related='tier_id.color', string='Tier Color')
    notes = fields.Char()
    #other details
    current_team = fields.Char("Current Team")
    jersy_size = fields.Char('Jersy Size')
    jersy_number = fields.Char("Number in Jersy")
    jersy_name = fields.Char("Name in Jersy")
    blood_group = fields.Char("Blood Group")
    p_type =   fields.Char("Type")
    p_category = fields.Char("Category")

    @api.model
    def get_sell_teams_data(self, player_id):
        """Return available teams + auction data for the web sell modal."""
        player = self.browse(int(player_id))
        auctions = self.env['auction.auction'].search([])
        teams = []
        for auction in auctions:
            if auction.remaining_players_count <= 0 or auction.remaining_points <= 0:
                continue

            # Compute effective base point for this player's tier
            effective_base = auction.base_point
            if player.tier_id and auction.tier_limit_ids:
                tier_limit = auction.tier_limit_ids.filtered(
                    lambda l: l.tier_id.id == player.tier_id.id
                )
                if tier_limit and tier_limit[0].base_point > 0:
                    effective_base = tier_limit[0].base_point

            # Tier limit remaining slots
            # Exclude the current player from the count to avoid stale-record false positives
            # (e.g. if a player was previously sold to this team without proper record cleanup).
            tier_slots_ok = True
            if player.tier_id and auction.tier_limit_ids:
                tier_limit = auction.tier_limit_ids.filtered(
                    lambda l: l.tier_id.id == player.tier_id.id
                )
                if tier_limit:
                    already_sold = self.env['auction.auction.player'].search_count([
                        ('auction_id', '=', auction.id),
                        ('player_id.tier_id', '=', player.tier_id.id),
                        ('player_id', '!=', player.id),
                    ])
                    if already_sold >= tier_limit[0].max_players:
                        tier_slots_ok = False

            # Check the team can actually afford the tier's minimum bid.
            # max_call is derived from the global base point; a tier's effective_base may be higher.
            budget_ok = (effective_base <= auction.max_call)

            slabs = [
                {'from_amount': s.from_amount, 'to_amount': s.to_amount, 'increment': s.increment}
                for s in auction.auction_bid_slab_ids.sorted('from_amount')
            ]

            teams.append({
                'team_id': auction.team_id.id,
                'team_name': auction.team_id.name,
                'auction_id': auction.id,
                'remaining_points': auction.remaining_points,
                'remaining_players': auction.remaining_players_count,
                'base_point': auction.base_point,
                'effective_base_point': effective_base,
                'max_call': auction.max_call,
                'tier_slots_ok': tier_slots_ok,
                'budget_ok': budget_ok,
                'slabs': slabs,
            })
        return teams

    @api.model
    def action_sell_from_web(self, player_id, team_id, final_point):
        """Execute sell from the web auction template. Returns dict with success/error."""
        player = self.browse(int(player_id))
        if not player.exists():
            return {'success': False, 'error': 'Player not found'}

        # Icon player guard
        icon_players = self.env['auction.team'].search([]).mapped('key_player_ids')
        if player.id in icon_players.ids:
            return {'success': False, 'error': '%s is an icon player and cannot be sold via auction' % player.name}

        auction = self.env['auction.auction'].search([('team_id', '=', int(team_id))], limit=1)
        if not auction:
            return {'success': False, 'error': 'Selected team is not part of the current auction'}

        # Tier limit check
        if player.tier_id and auction.tier_limit_ids:
            tier_limit = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            if tier_limit:
                already_sold = self.env['auction.auction.player'].search_count([
                    ('auction_id', '=', auction.id),
                    ('player_id.tier_id', '=', player.tier_id.id),
                ])
                if already_sold >= tier_limit[0].max_players:
                    return {
                        'success': False,
                        'error': '%s has already reached the maximum of %d player(s) from the "%s" tier' % (
                            auction.team_id.name, tier_limit[0].max_players, player.tier_id.name
                        )
                    }

        # Effective base point (tier-specific)
        effective_base = auction.base_point
        if player.tier_id and auction.tier_limit_ids:
            tier_limit = auction.tier_limit_ids.filtered(lambda l: l.tier_id.id == player.tier_id.id)
            if tier_limit and tier_limit[0].base_point > 0:
                effective_base = tier_limit[0].base_point

        if final_point < effective_base:
            return {'success': False, 'error': 'Points cannot be below the base point of %d' % effective_base}

        # Budget safety check
        remaining_players = auction.remaining_players_count
        budget_max = auction.remaining_points - ((remaining_players - 1) * auction.base_point)
        if final_point > budget_max:
            return {'success': False, 'error': 'Budget exceeded! Maximum allowed for this player: %d pts' % budget_max}

        # Max points cap
        if auction.max_limited == 'yes' and final_point > auction.max_points:
            return {'success': False, 'error': 'Points exceed the auction cap of %d' % auction.max_points}

        # Execute the sell
        auction_line_data = {'player_id': player.id, 'points': final_point}
        message = '%s sold to %s for %d points!' % (player.name, auction.team_id.name, final_point)

        existing = self.env['auction.auction.player'].search([('player_id', '=', player.id)])
        if not existing:
            auction.player_ids = [(0, 0, auction_line_data)]
            player.assigned_team_id = auction.team_id.id
            player.state = 'sold'
            # is_on_stage stays True so the live board can show the SOLD stamp
            # until the next player is called via get_random_player()
            player.create_auction_history(auction.team_id.id, message, tournament_id=player.tournament_id.id, player=player)
        else:
            auction_line_data['auction_id'] = auction.id
            existing.write(auction_line_data)

        self.env.user.notify_success(message=message, title='CONGRATULATIONS!')
        return {
            'success': True,
            'message': message,
            'player_id': player.id,
            'player_name': player.name,
            'team_id': auction.team_id.id,
            'team_name': auction.team_id.name,
            'final_point': final_point,
            'display_seconds': player.tournament_id.sold_display_seconds if player.tournament_id else 5,
        }

    def print_player_cards(self):
        tournament = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        template = tournament.player_display_template if tournament else 'vanilla'
        report_map = {
            'vanilla':       'auction_module.action_report_player_card',
            'butterscotch':  'auction_module.action_report_player_card_butterscotch',
            'strawberry':    'auction_module.action_report_player_card_strawberry',
            'cherry':        'auction_module.action_report_player_card_cherry',
            'pistah':        'auction_module.action_report_player_card_pistah',
        }
        report_ref = report_map.get(template, 'auction_module.action_report_player_card')
        return self.env.ref(report_ref).report_action(self)

    # def print_player_card(self):
    #     players = self.search([])
    #     return self.env.ref('auction_module.action_player_card_auction').report_action(players.ids)

    @api.model
    def action_player_card_report(self):
        tournament = self.env['auction.tournament'].search([('active', '=', True)], limit=1)
        template = tournament.player_display_template if tournament else 'vanilla'
        report_map = {
            'vanilla':      'auction_module.report_player_card_list',
            'butterscotch': 'auction_module.report_player_card_list_butterscotch',
            'strawberry':   'auction_module.report_player_card_list_strawberry',
            'cherry':       'auction_module.report_player_card_list_cherry',
            'pistah':       'auction_module.report_player_card_list_pistah',
        }
        report_name = report_map.get(template, 'auction_module.report_player_card_list')
        return {
            'type': 'ir.actions.report',
            'report_name': report_name,
            'report_type': 'qweb-pdf',
            'data': {'model': 'auction.team.player'},
        }

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

        if vals.get('photo_url', False):
            image_base64 = self.get_base64_from_url(vals.get('photo_url', False))
            if image_base64:
               vals.update({'photo': image_base64})

        if not vals.get('payment_url', False):
            vals.update({'amount_paid': False})
        player = super(AuctionTeamPlayer, self).create(vals)
        print(vals, "After printing vals")
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

        players = self.get_auction_players()
        if players:
            player_ids = players.ids
            if tournament_id.player_appearance_algorithm == 'random':
                random_player_id = random.choice(player_ids)
                random_player = self.browse(random_player_id)
            else:
                random_player = self.browse(player_ids[0])

        # ── Stage tracking: clear all, mark only the selected player ──
        on_stage = self.search([('is_on_stage', '=', True)])
        if on_stage:
            on_stage.sudo().write({'is_on_stage': False})
        if random_player:
            random_player.sudo().write({'is_on_stage': True})

        return random_player

    def action_unsold(self):
        for player in self:
            if player.state == 'auction':
                player.state = 'unsold'
                # is_on_stage stays True so the live board shows the UNSOLD stamp
                # until the next player is called via get_random_player()
                message = player.name + ' is Unsold!'
                player.create_unsold_auction_history( message, tournament_id=player.tournament_id.id,
                                              player=player)
                self.env.user.notify_success(message)
        display_seconds = self[0].tournament_id.sold_display_seconds if self and self[0].tournament_id else 5
        return {
            'success': True,
            'display_seconds': display_seconds if display_seconds and display_seconds > 0 else 5,
        }

    def action_recall_auction_sold(self):
        context = self.env.context.copy()
        for player in self:
            if player.state == 'sold':
                auction_player = self.env['auction.auction.player'].search([('player_id', '=', player.id)])
                if auction_player:
                    auction_player.action_recall_to_auction()
        if context.get('mass_update', False):
            message =  'Selected players brought back to auction successfully!. The player will be available in the auction'
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
                    'tier_id': player.previous_tier_id.id if player.previous_tier_id else False,
                    'previous_tier_id': False,
                })
                team_id.key_player_ids = [(3, player.id)]
                message = player.name + ' has been revoked from icon player list and brought back to auction successfully!'
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
        # is_on_stage stays True — cleared on next player call
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
