/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

const { Component, hooks } = owl;
const { useState, onWillStart, onMounted, onWillUnmount } = hooks;

/**
 * Navbar tournament badge. Auction Users with several Organizer Tournaments
 * get a dropdown to switch Active Tournament (SaaS replaces this widget).
 */
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
            tournamentId: false,
            tournaments: [],
            canSwitch: false,
            expanded: false,
            switching: false,
            auctionRulesReady: false,
        });

        onWillStart(async () => {
            await this.loadTournaments();
        });

        const onOutsideClick = (ev) => {
            const root = this.el;
            if (!root || root.contains(ev.target)) {
                return;
            }
            this.state.expanded = false;
        };
        onMounted(() => document.addEventListener("click", onOutsideClick));
        onWillUnmount(() => document.removeEventListener("click", onOutsideClick));
    }

    async loadTournaments() {
        try {
            const data = await this.orm.call("res.users", "get_systray_tournaments", []);
            this.applyPayload(data || {});
        } catch (_e) {
            this.state.tournamentName = "";
            this.state.tournaments = [];
            this.state.canSwitch = false;
            this.state.projectorUrl = "";
            this.state.showcaseUrl = "";
            this.state.liveBoardUrl = "";
        }
    }

    applyPayload(data) {
        const current = data.current || null;
        const items = data.tournaments || [];
        this.state.tournaments = items;
        this.state.canSwitch = Boolean(data.can_switch);
        if (current) {
            this.state.tournamentId = current.id;
            this.state.tournamentName = current.name || "";
            this.state.tournamentLogo = current.logo || "";
            const rulesReady = Boolean(current.has_auction_rules);
            this.state.auctionRulesReady = rulesReady;
            this.state.projectorUrl = rulesReady ? (current.projector_url || "") : "";
            this.state.showcaseUrl = rulesReady ? "/auction/showcase" : "";
            this.state.liveBoardUrl = current.live_board_url || "/auction/my/live-board";
        } else {
            this.state.tournamentId = false;
            this.state.tournamentName = "";
            this.state.tournamentLogo = "";
            this.state.projectorUrl = "";
            this.state.showcaseUrl = "";
            this.state.liveBoardUrl = "";
            this.state.auctionRulesReady = false;
        }
    }

    onBadgeClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (this.state.canSwitch) {
            if (this.state.switching) {
                return;
            }
            this.state.expanded = !this.state.expanded;
            return;
        }
        if (window.innerWidth <= 767) {
            this.state.expanded = !this.state.expanded;
        }
    }

    async onSelectTournament(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (this.state.switching) {
            return;
        }
        const tournamentId = parseInt(ev.currentTarget.getAttribute("data-tournament-id"), 10);
        if (!tournamentId) {
            return;
        }
        const item = this.state.tournaments.find((t) => t.id === tournamentId);
        if (!item || item.active) {
            this.state.expanded = false;
            return;
        }
        this.state.switching = true;
        try {
            await this.orm.call("res.users", "set_active_tournament", [
                [session.uid],
                tournamentId,
            ]);
            window.location.reload();
        } catch (_e) {
            this.state.switching = false;
            this.state.expanded = false;
            this.notification.add(
                "Could not switch tournament. Please try again.",
                { type: "danger", title: "Tournament" }
            );
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
