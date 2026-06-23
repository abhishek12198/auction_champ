/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

const { Component, hooks } = owl;
const { useState, onWillStart } = hooks;

class TournamentSystrayItem extends Component {
    setup() {
        this.orm = useService("orm");
        this.state = useState({ tournamentName: "", tournamentLogo: "" });

        onWillStart(async () => {
            try {
                const result = await this.orm.read(
                    "res.users",
                    [session.uid],
                    ["tournament_id"]
                );
                if (result && result[0] && result[0].tournament_id) {
                    const tId = result[0].tournament_id[0];
                    const tName = result[0].tournament_id[1];
                    this.state.tournamentName = tName;
                    this.state.tournamentLogo = "/web/image/auction.tournament/" + tId + "/logo";
                }
            } catch (_e) {
                // leave blank on any error
            }
        });
    }
}

TournamentSystrayItem.template = "auction_module.TournamentSystrayItem";

// sequence 51 → renders just to the left of mail.MessagingMenu (default seq 50)
// NavBar reverses the sorted list, so seq 51 appears just before (left of) chat icon
registry.category("systray").add(
    "auction.tournament_systray",
    { Component: TournamentSystrayItem },
    { sequence: 51 }
);
