/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

const { Component, hooks } = owl;
const { useState, onWillStart, onMounted, onWillUnmount, onPatched } = hooks;

/**
 * Navbar tournament badge. Auction Users with several Organizer Tournaments
 * get a dropdown to switch Active Tournament (SaaS replaces this widget).
 */
class TournamentSystrayItem extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
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
        const onReposition = () => this._positionMobileMenu();
        onMounted(() => {
            document.addEventListener("click", onOutsideClick);
            window.addEventListener("resize", onReposition);
            this._positionMobileMenu();
        });
        onPatched(() => this._positionMobileMenu());
        onWillUnmount(() => {
            document.removeEventListener("click", onOutsideClick);
            window.removeEventListener("resize", onReposition);
        });
    }

    _positionMobileMenu() {
        const menu = this.el && this.el.querySelector(".o_auction_tournament_menu");
        if (!menu) {
            return;
        }
        if (window.innerWidth > 767) {
            menu.style.position = "";
            menu.style.top = "";
            menu.style.left = "";
            menu.style.right = "";
            menu.style.width = "";
            menu.style.minWidth = "";
            menu.style.maxWidth = "";
            menu.style.transform = "";
            return;
        }
        const navbar = document.querySelector(".o_main_navbar");
        const badge = this.el.querySelector(".o_auction_tournament_badge");
        const navBottom = navbar ? navbar.getBoundingClientRect().bottom : 46;
        const badgeBottom = badge ? badge.getBoundingClientRect().bottom : navBottom;
        menu.style.position = "fixed";
        menu.style.top = `${Math.round(Math.max(navBottom, badgeBottom) + 8)}px`;
        menu.style.left = "12px";
        menu.style.right = "12px";
        menu.style.width = "auto";
        menu.style.minWidth = "0";
        menu.style.maxWidth = "none";
        menu.style.transform = "none";
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
            const data = await this.orm.call("res.users", "set_active_tournament", [
                [session.uid],
                tournamentId,
            ]);
            this.applyPayload(data || {});
            this.state.expanded = false;
            await this._refreshAfterSwitch();
        } catch (_e) {
            this.state.expanded = false;
            this.notification.add(
                "Could not switch tournament. Please try again.",
                { type: "danger", title: "Tournament" }
            );
        } finally {
            this.state.switching = false;
        }
    }

    async _refreshAfterSwitch() {
        const hash = (window.location.hash || "").replace(/^#/, "");
        let actionId = 0;
        hash.split("&").forEach((part) => {
            const bits = part.split("=");
            if (bits[0] === "action") {
                actionId = parseInt(bits[1], 10) || 0;
            }
        });
        if (actionId && this.action) {
            try {
                await this.action.doAction(actionId, {
                    clearBreadcrumbs: true,
                    additionalContext: { ac_working_switch: Date.now() },
                });
                return;
            } catch (_e) {
                // Fall through to a full reload if the current action cannot remount.
            }
        }
        window.location.reload();
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
