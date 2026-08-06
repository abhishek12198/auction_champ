/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

const { Component, hooks } = owl;
const { useState, onWillStart, onMounted, onWillUnmount } = hooks;

function buildLiveBoardUrl(slug) {
    if (!slug) {
        return "";
    }
    const db = session.db || session.db_name || "";
    if (db) {
        return "/" + db + "/" + slug + "/auction/live-board";
    }
    // Slug-only route redirects to the db-prefixed URL
    return "/" + slug + "/auction/live-board";
}

class TournamentSystrayItem extends Component {
    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            tournamentName: "",
            tournamentLogo: "",
            projectorUrl: "",
            showcaseUrl: "",
            liveBoardUrl: "",
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
                if (!(result && result[0] && result[0].tournament_id)) {
                    return;
                }
                const tId = result[0].tournament_id[0];
                const tName = result[0].tournament_id[1];
                this.state.tournamentName = tName;
                this.state.tournamentLogo = "/web/image/auction.tournament/" + tId + "/logo";

                let tRow = null;
                try {
                    const tRes = await this.orm.read(
                        "auction.tournament",
                        [tId],
                        ["projector_url", "live_board_url", "slug", "has_auction_rules"]
                    );
                    tRow = tRes && tRes[0];
                } catch (_missingField) {
                    // live_board_url may be missing until module upgrade
                    try {
                        const tRes = await this.orm.read(
                            "auction.tournament",
                            [tId],
                            ["projector_url", "slug", "has_auction_rules"]
                        );
                        tRow = tRes && tRes[0];
                    } catch (_e2) {
                        tRow = null;
                    }
                }

                if (!tRow) {
                    return;
                }

                const rulesReady = Boolean(tRow.has_auction_rules);
                this.state.auctionRulesReady = rulesReady;
                if (rulesReady) {
                    this.state.showcaseUrl = "/auction/showcase";
                    this.state.projectorUrl = tRow.projector_url || "";
                    if (!this.state.projectorUrl && tRow.slug && session.db) {
                        this.state.projectorUrl =
                            "/" + session.db + "/auction/projector/" + tRow.slug + "/";
                    }
                } else {
                    this.state.showcaseUrl = "";
                    this.state.projectorUrl = "";
                }

                // Third navbar icon — same place as Console / Projector
                this.state.liveBoardUrl =
                    tRow.live_board_url || buildLiveBoardUrl(tRow.slug) || "/auction/my/live-board";
            } catch (_e) {
                // leave blank on any error
            }
        });

        const onOutsideClick = (ev) => {
            if (this.state.expanded && this.el && !this.el.contains(ev.target)) {
                this.state.expanded = false;
            }
        };
        onMounted(() => document.addEventListener("click", onOutsideClick, true));
        onWillUnmount(() => document.removeEventListener("click", onOutsideClick, true));
    }

    onBadgeClick(ev) {
        if (window.innerWidth <= 767) {
            ev.stopPropagation();
            this.state.expanded = !this.state.expanded;
        }
    }

    onProjectorClick(ev) {
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

registry.category("systray").add(
    "auction.tournament_systray",
    { Component: TournamentSystrayItem },
    { sequence: 51 }
);
