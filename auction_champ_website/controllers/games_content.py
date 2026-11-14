# -*- coding: utf-8 -*-
"""Public copy for the Games hub and each sport page.

The fields named here match the player profile Auction Champ actually stores
for that tournament type.
"""

GAMES = [
    {
        'slug': 'cricket',
        'name': 'Cricket',
        'page_key': 'website_game_cricket',
        'image': '/auction_champ_website/static/src/img/games/cricket.jpg',
        'image_alt': 'A cricketer in navy playing a shot on a sunlit pitch',
        'card': 'Sell batters, bowlers, all-rounders and wicket-keepers from a live stage.',
        'h1': 'Cricket player auction software',
        'lead': (
            'Run the auction the way a cricket league buys a squad. One player '
            'comes on stage with a photo, a role and a base price. Teams bid '
            'from a purse until the squad is full.'
        ),
        'sections': [
            {
                'title': 'Made for a cricket auction night',
                'paragraphs': [
                    'Club leagues, corporate tournaments and franchise-style cricket sides already know the format. Players are called in an order, the room hears the base price, and a team buys the player or the player stays unsold.',
                    'Auction Champ keeps that night on one screen. The hall can follow the player on a projector. Team owners see the same player, the current bid and what is left in the purse.',
                ],
            },
            {
                'title': 'What the cricket player card carries',
                'paragraphs': [
                    'A cricket tournament records the batting style and the bowling style, plus the playing role you give that player. Those details sit with the photo, the base price and the tier, so a captain can decide before the bid moves.',
                    'Typical roles are batter, bowler, all-rounder and wicket-keeper. The role is yours to set for each player, so a league can use the names its auctioneer already calls.',
                ],
            },
            {
                'title': 'From registration to the last player',
                'paragraphs': [
                    'Players join through a registration link. You group them into tiers, set a base price, and give each team a purse and a squad size. On the night, the auctioneer brings one player on stage.',
                    'A team buys the player, or the player is marked unsold and can be called again later. When the auction is done, the bid summary shows who bought whom and what each purse has left.',
                ],
            },
        ],
        'details_title': 'On a cricket player card',
        'details': [
            'Batting style',
            'Bowling style',
            'Playing role',
            'Photo, base price and tier',
            'Team purse and squad size',
        ],
        'faqs': [
            {
                'q': 'Can a local cricket league run a franchise-style player auction?',
                'a': 'Yes. You create the teams, give each team a purse and a squad size, then call players one by one. The winning bid is recorded against that team.',
            },
            {
                'q': 'Does the live display show batting and bowling style?',
                'a': 'Yes. Cricket tournaments store batting style and bowling style with the player, and those details travel onto the player card the room is watching.',
            },
            {
                'q': 'What happens to an unsold cricketer?',
                'a': 'The player is marked unsold and can be brought back into the auction later. The purse of every team stays visible while you do it.',
            },
        ],
    },
    {
        'slug': 'football',
        'name': 'Football',
        'page_key': 'website_game_football',
        'image': '/auction_champ_website/static/src/img/games/football.jpg',
        'image_alt': 'A footballer in navy striking the ball on a lit pitch',
        'card': 'Buy a balanced side by position, preferred foot and work rate.',
        'h1': 'Football player auction software',
        'lead': (
            'Fill eleven positions without losing track of the purse. Auction '
            'Champ records where a footballer plays, then sells that player '
            'live to a team.'
        ),
        'sections': [
            {
                'title': 'Buy the side, not just the names',
                'paragraphs': [
                    'A football auction fails when every team chases the same forwards and nobody is left to keep goal. The useful card is the one that says the position before the bidding starts.',
                    'Auction Champ is set up for that. Each footballer has a main position and any secondary positions, so the room can see a goalkeeper, a centre back or a striker before the first bid.',
                ],
            },
            {
                'title': 'What the football player card carries',
                'paragraphs': [
                    'The profile stores the playing position, secondary positions and preferred foot. You can also keep age, height, weight, playing style, strengths and work rate. Those are the notes a coach asks for when the purse is tight.',
                    'Positions cover the line: goalkeeper, centre back, left back, right back, defensive midfielder, central midfielder, attacking midfielder, left winger, right winger and striker.',
                ],
            },
            {
                'title': 'How auction night works',
                'paragraphs': [
                    'Open registration, set tiers and base prices, then give every franchise a purse and a squad limit. On the night the auctioneer calls one player. Teams bid, and the sale stops when a team buys the player or the player is left unsold.',
                    'The projector shows the player to the hall. Owners follow the same bid. At the end, the bid summary is the squad list with the points each team still holds.',
                ],
            },
        ],
        'details_title': 'On a football player card',
        'details': [
            'Main position and secondary positions',
            'Preferred foot',
            'Age, height and weight',
            'Playing style, strengths and work rate',
            'Team purse and squad size',
        ],
        'faqs': [
            {
                'q': 'Can teams see a player’s position before they bid?',
                'a': 'Yes. Football tournaments store a main position and secondary positions on the player. That card is what the auction floor shows.',
            },
            {
                'q': 'Which positions can I record?',
                'a': 'Goalkeeper, centre back, left back, right back, defensive, central and attacking midfield, both wings, and striker.',
            },
            {
                'q': 'Can I stop a team from buying more players than the squad allows?',
                'a': 'Yes. Each team has a purse and a squad size. The auction follows those limits while players are sold.',
            },
        ],
    },
    {
        'slug': 'kabaddi',
        'name': 'Kabaddi',
        'page_key': 'website_game_kabaddi',
        'image': '/auction_champ_website/static/src/img/games/kabaddi.jpg',
        'image_alt': 'A kabaddi raider lunging toward a line of defenders',
        'card': 'Build the side from riders, defenders and all-rounders.',
        'h1': 'Kabaddi player auction software',
        'lead': (
            'A kabaddi team is a chain of defenders and a raider who can get '
            'back. Auction Champ sells each player with that role on the card, '
            'live, against a team purse.'
        ),
        'sections': [
            {
                'title': 'Raiders and the chain behind them',
                'paragraphs': [
                    'Kabaddi auctions are short and loud. The room wants to know, before the bid, whether the player raids or defends. A list of names is not enough for a seven-a-side squad.',
                    'When you create a kabaddi tournament, every player is a Defender, a Rider or an All-rounder. Rider is the raiding role. That label is on the card the hall is watching.',
                ],
            },
            {
                'title': 'What the kabaddi player card carries',
                'paragraphs': [
                    'The role sits with the photo, the base price and the tier. Teams still bid from a purse, and the squad size still caps how many players a franchise can buy.',
                    'Use the same auction floor as a cricket or football night. Only the player card changes, so a kabaddi auctioneer is not forced into cricket fields such as batting style.',
                ],
            },
            {
                'title': 'Registration through the final raid',
                'paragraphs': [
                    'Share a registration link, sort players into tiers, and set the base price. On auction night the projector puts one player on stage. Teams bid. You sell the player or mark the player unsold.',
                    'Unsold players can return later in the night. The bid summary afterwards shows the squad each team actually bought.',
                ],
            },
        ],
        'details_title': 'On a kabaddi player card',
        'details': [
            'Defender, Rider or All-rounder',
            'Photo, base price and tier',
            'Team purse and squad size',
            'Live stage and hall projector',
            'Sold and unsold, with a bid summary',
        ],
        'faqs': [
            {
                'q': 'Which kabaddi roles can I assign?',
                'a': 'Defender, Rider and All-rounder. Rider is the raider. The role is stored on the player and shown on the auction card.',
            },
            {
                'q': 'Is this a separate tool from the cricket auction?',
                'a': 'No. It is the same Auction Champ tournament. You choose Kabaddi as the game, and the player card uses kabaddi roles instead of cricket or football fields.',
            },
            {
                'q': 'Can an unsold raider be called again?',
                'a': 'Yes. Mark the player unsold and bring that player back when you are ready. Team purses stay up to date.',
            },
        ],
    },
    {
        'slug': 'badminton',
        'name': 'Badminton',
        'page_key': 'website_game_badminton',
        'image': '/auction_champ_website/static/src/img/games/badminton.jpg',
        'image_alt': 'A badminton player hitting a smash on an indoor court',
        'card': 'Auction singles, doubles and mixed-doubles players with style and level.',
        'h1': 'Badminton player auction software',
        'lead': (
            'A badminton franchise needs the event, not only the name. Auction '
            'Champ records singles, doubles or mixed doubles, then sells that '
            'player live.'
        ),
        'sections': [
            {
                'title': 'A roster across five events',
                'paragraphs': [
                    'Badminton auctions are different from a cricket auction. One player might be a men’s doubles specialist and a poor fit for mixed. The card has to say that before anyone spends the purse.',
                    'Auction Champ stores the category on the player: Men’s Singles, Men’s Doubles, Women’s Singles, Women’s Doubles or Mixed Doubles. Teams see it on the live card.',
                ],
            },
            {
                'title': 'What the badminton player card carries',
                'paragraphs': [
                    'Along with the category, you can record playing style (attacking, defensive or all-round), skill level from beginner to professional, and the playing hand.',
                    'Photo, base price and tier stay on the card. The purse and the squad size work the same way they do for the other sports, so the auctioneer is not learning a second product.',
                ],
            },
            {
                'title': 'How a badminton auction runs',
                'paragraphs': [
                    'Players register, you place them in tiers, and each franchise gets a purse. On the night one player is on stage. The hall sees the category and the level while the bid climbs.',
                    'Sell the player to a team or mark the player unsold. The projector is there for the hall, and the bid summary is there when the last player is done.',
                ],
            },
        ],
        'details_title': 'On a badminton player card',
        'details': [
            'Men’s and women’s singles and doubles, and mixed doubles',
            'Attacking, defensive or all-round style',
            'Level, from beginner to professional',
            'Playing hand',
            'Team purse and squad size',
        ],
        'faqs': [
            {
                'q': 'Can I auction doubles players separately from singles players?',
                'a': 'Yes. Each player has a category: men’s or women’s singles, men’s or women’s doubles, or mixed doubles. That category is on the live card.',
            },
            {
                'q': 'Can I show whether a player is a beginner or a professional?',
                'a': 'Yes. Badminton players have a level: beginner, intermediate, advanced or professional, plus an attacking, defensive or all-round style.',
            },
            {
                'q': 'Do team purses work the same as in a cricket auction?',
                'a': 'Yes. Each team has a purse and a squad size. Bids are taken live, and a sold player is charged to that team.',
            },
        ],
    },
]


def public_game_cards():
    """Short cards for the homepage and the games hub."""
    return [
        {
            'name': game['name'],
            'slug': game['slug'],
            'href': '/games/%s' % game['slug'],
            'image': game['image'],
            'image_alt': game['image_alt'],
            'card': game['card'],
        }
        for game in GAMES
    ]


def game_by_slug(slug):
    for game in GAMES:
        if game['slug'] == slug:
            return game
    return None
