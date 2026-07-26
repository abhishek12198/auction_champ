/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

const { Component, hooks } = owl;
const { useState, onWillStart, onMounted, onWillUnmount } = hooks;

class TournamentSystrayItem extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            tournamentName: "",
            tournamentLogo: "",
            projectorUrl: "",
            showcaseUrl: "",
            auctionRulesReady: false,
            expanded: false,
        });

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

                    try {
                        const tRes = await this.orm.read(
                            "auction.tournament",
                            [tId],
                            ["projector_url", "slug", "has_auction_rules"]
                        );
                        const tRow = tRes && tRes[0];
                        const rulesReady = Boolean(tRow && tRow.has_auction_rules);
                        this.state.auctionRulesReady = rulesReady;
                        if (rulesReady) {
                            this.state.showcaseUrl = "/auction/showcase";
                            this.state.projectorUrl = (tRow && tRow.projector_url) || "";
                            if (!this.state.projectorUrl && tRow && tRow.slug && session.db) {
                                this.state.projectorUrl =
                                    "/" + session.db + "/auction/projector/" + tRow.slug + "/";
                            }
                        } else {
                            this.state.showcaseUrl = "";
                            this.state.projectorUrl = "";
                        }
                    } catch (_e2) {
                        this.state.projectorUrl = "";
                        this.state.showcaseUrl = "";
                        this.state.auctionRulesReady = false;
                    }
                }
            } catch (_e) {
                // leave blank on any error
            }
        });

        // Close the mobile tooltip when the user taps outside the badge
        const onOutsideClick = (ev) => {
            if (this.state.expanded && this.el && !this.el.contains(ev.target)) {
                this.state.expanded = false;
            }
        };
        onMounted(() => document.addEventListener("click", onOutsideClick, true));
        onWillUnmount(() => document.removeEventListener("click", onOutsideClick, true));
    }

    onBadgeClick(ev) {
        // Only toggle on mobile (≤767px); on desktop the name is always visible
        if (window.innerWidth <= 767) {
            ev.stopPropagation();
            this.state.expanded = !this.state.expanded;
        }
    }

    onProjectorClick(ev) {
        // Don't trigger the badge expanded/collapse logic
        ev.stopPropagation();
    }

    onRulesRequiredClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.notification.add(
            "Set Auction Rules for this tournament before opening Player Console or Projector.",
            { type: "warning", title: "Auction Rules Required" }
        );
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
