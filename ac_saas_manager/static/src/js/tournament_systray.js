/** @odoo-module **/

import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { session } from "@web/session";

const { Component, hooks } = owl;
const { useState, onMounted, onWillUnmount, onPatched } = hooks;

/**
 * Replaces auction_module tournament badge with a switcher over all
 * tournaments owned / assigned to the logged-in SaaS user.
 * Also shows the active SaaS plan chip.
 */
class SaasTournamentSystrayItem extends Component {
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            tournamentName: "",
            tournamentLogo: "",
            projectorUrl: "",
            showcaseUrl: "",
            tournamentId: false,
            tournaments: [],
            hasMoreTournaments: false,
            tournamentTotal: 0,
            canSwitch: false,
            expanded: false,
            switching: false,
            pickerOpen: false,
            pickerQuery: "",
            pickerResults: [],
            pickerLoading: false,
            pickerTotal: 0,
            auctionRulesReady: false,
            planAccountId: false,
            planName: "",
            planAccount: "",
            planExpiry: "",
            planTitle: "",
            planLines: [],
            planCanUpgrade: false,
            planExpanded: false,
            upgrading: false,
            parallelSessions: false,
            workingScopeHint: "",
            expiryWarning: false,
            expiryMessage: "",
            expiryUrgent: false,
            accountFrozen: false,
            canRequestRenewal: false,
            reactivating: false,
        });

        // Bubble phase so button handlers run before "outside click" closes menus
        const onOutsideClick = (ev) => {
            const root = this.el;
            if (!root || root.contains(ev.target)) {
                return;
            }
            if (this.state.pickerOpen) {
                return;
            }
            this.state.expanded = false;
            this.state.planExpanded = false;
        };
        const onReposition = () => this._positionMobileMenu();
        onMounted(() => {
            // Load after shell paints — do not block navbar / first action on this RPC.
            this.loadTournaments();
            document.addEventListener("click", onOutsideClick);
            window.addEventListener("resize", onReposition);
            this._applyFrozenUi();
            this._positionMobileMenu();
        });
        onPatched(() => this._positionMobileMenu());
        onWillUnmount(() => {
            document.removeEventListener("click", onOutsideClick);
            window.removeEventListener("resize", onReposition);
            if (this._pickerSearchTimer) {
                clearTimeout(this._pickerSearchTimer);
            }
        });
    }

    _positionMobileMenu() {
        const menu = this.el && this.el.querySelector(".o_saas_tournament_menu");
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
        const badge = this.el.querySelector(".o_saas_tournament_badge, .o_auction_tournament_badge");
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

    _applyFrozenUi() {
        const frozen = Boolean(this.state.accountFrozen || session.saas_account_frozen);
        document.body.classList.toggle("o_saas_account_frozen", frozen);
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
            this.state.planAccountId = false;
            this.state.planName = "";
            this.state.planLines = [];
            this.state.planCanUpgrade = false;
            this.state.expiryWarning = false;
            this.state.expiryMessage = "";
            this.state.expiryUrgent = false;
            this.state.accountFrozen = false;
            this.state.canRequestRenewal = false;
        }
    }

    applyPayload(data) {
        const current = data.current || null;
        const items = data.tournaments || [];
        this.state.tournaments = items;
        this.state.tournamentTotal = Number(data.tournament_total || items.length || 0);
        this.state.hasMoreTournaments = Boolean(data.has_more_tournaments);
        this.state.canSwitch = Boolean(data.can_switch) && !Boolean(data.account_frozen);
        this.state.parallelSessions = Boolean(data.parallel_sessions);
        this.state.workingScopeHint = data.working_scope_hint || "";
        this.state.accountFrozen = Boolean(data.account_frozen);
        this.state.canRequestRenewal = Boolean(data.can_request_renewal);
        if (data.saas_account_id) {
            this.state.planAccountId = data.saas_account_id;
        }
        if (current) {
            this.state.tournamentId = current.id;
            this.state.tournamentName = current.name || "";
            this.state.tournamentLogo = current.logo || "";
            const rulesReady = Boolean(current.has_auction_rules);
            this.state.auctionRulesReady = rulesReady;
            this.state.projectorUrl = rulesReady ? (current.projector_url || "") : "";
            this.state.showcaseUrl = (!this.state.accountFrozen && rulesReady) ? "/auction/showcase" : "";
        } else {
            this.state.tournamentId = false;
            this.state.tournamentName = "";
            this.state.tournamentLogo = "";
            this.state.projectorUrl = "";
            this.state.showcaseUrl = "";
            this.state.auctionRulesReady = false;
        }

        const plan = data.plan || null;
        if (plan && plan.name) {
            this.state.planAccountId = plan.account_id || this.state.planAccountId || false;
            this.state.planName = plan.name;
            this.state.planAccount = plan.account_name || "";
            this.state.planExpiry = plan.expiry_display || "";
            this.state.planLines = plan.lines || [];
            this.state.planCanUpgrade = Boolean(plan.can_upgrade) && !this.state.accountFrozen;
            this.state.planTitle = plan.can_upgrade
                ? `Current plan: ${plan.name} — click for details / upgrade`
                : `Current plan: ${plan.name}`;
        } else {
            this.state.planName = this.state.planName || "";
            this.state.planAccount = "";
            this.state.planExpiry = "";
            this.state.planLines = [];
            this.state.planCanUpgrade = false;
            this.state.planTitle = "";
        }

        const expiry = data.expiry_warning || null;
        if (expiry && expiry.message) {
            this.state.expiryWarning = true;
            this.state.expiryMessage = expiry.message;
            this.state.expiryUrgent = Boolean(expiry.urgent || expiry.frozen);
        } else if (this.state.accountFrozen) {
            this.state.expiryWarning = true;
            this.state.expiryMessage =
                "Your account has expired and is frozen. Request reactivation to continue.";
            this.state.expiryUrgent = true;
        } else {
            this.state.expiryWarning = false;
            this.state.expiryMessage = "";
            this.state.expiryUrgent = false;
        }
        this._applyFrozenUi();
    }

    onBadgeClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (!this.state.canSwitch || this.state.switching) {
            return;
        }
        this.state.planExpanded = false;
        this.state.expanded = !this.state.expanded;
    }

    onPlanClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.expanded = false;
        this.state.planExpanded = !this.state.planExpanded;
    }

    onPlanMenuClick(ev) {
        // Keep the dropdown open when interacting inside it
        ev.stopPropagation();
    }

    async onRequestUpgrade(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (this.state.upgrading) {
            return;
        }
        if (!this.state.planAccountId) {
            this.notification.add("No SaaS account found for this login.", {
                title: "Upgrade",
                type: "danger",
            });
            return;
        }

        this.state.upgrading = true;
        try {
            const action = await this.orm.call(
                "ac.saas.account",
                "action_open_upgrade_wizard",
                [[this.state.planAccountId]],
                {
                    trigger_feature: "other",
                    tournament_id: this.state.tournamentId || false,
                }
            );
            this.state.planExpanded = false;
            if (action) {
                await this.action.doAction(action);
            }
        } catch (e) {
            const msg =
                (e && e.data && e.data.message) ||
                (e && e.message) ||
                "Could not open the upgrade request form.";
            this.notification.add(String(msg), {
                title: "Upgrade",
                type: "danger",
            });
        } finally {
            this.state.upgrading = false;
        }
    }

    async onRequestReactivation(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (this.state.reactivating) {
            return;
        }
        if (!this.state.planAccountId) {
            this.notification.add("No SaaS account found for this login.", {
                title: "Reactivation",
                type: "danger",
            });
            return;
        }
        this.state.reactivating = true;
        try {
            const action = await this.orm.call(
                "ac.saas.account",
                "action_request_reactivation",
                [[this.state.planAccountId]]
            );
            if (action) {
                await this.action.doAction(action);
            }
        } catch (e) {
            const msg =
                (e && e.data && e.data.message) ||
                (e && e.message) ||
                "Could not submit the reactivation request.";
            this.notification.add(String(msg), {
                title: "Reactivation",
                type: "danger",
            });
        } finally {
            this.state.reactivating = false;
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
        const fromMenu = this.state.tournaments.find((t) => t.id === tournamentId);
        const fromPicker = this.state.pickerResults.find((t) => t.id === tournamentId);
        const item = fromMenu || fromPicker;
        if (item && item.active) {
            this.state.expanded = false;
            this.closePicker();
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
            this.closePicker();
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

    onSearchMoreClick(ev) {
        ev.preventDefault();
        ev.stopPropagation();
        this.state.expanded = false;
        this.state.planExpanded = false;
        this.openPicker();
    }

    openPicker() {
        this.state.pickerOpen = true;
        this.state.pickerQuery = "";
        this.state.pickerResults = [];
        this.state.pickerTotal = 0;
        this._runPickerSearch("");
    }

    closePicker(ev) {
        if (ev) {
            ev.preventDefault();
            ev.stopPropagation();
        }
        this.state.pickerOpen = false;
        this.state.pickerQuery = "";
        this.state.pickerResults = [];
        this.state.pickerLoading = false;
    }

    onPickerBackdropClick(ev) {
        if (ev.target === ev.currentTarget) {
            this.closePicker();
        }
    }

    onPickerQueryInput(ev) {
        const value = (ev.target && ev.target.value) || "";
        this.state.pickerQuery = value;
        if (this._pickerSearchTimer) {
            clearTimeout(this._pickerSearchTimer);
        }
        this._pickerSearchTimer = setTimeout(() => {
            this._runPickerSearch(value);
        }, 220);
    }

    async _runPickerSearch(query) {
        this.state.pickerLoading = true;
        try {
            const data = await this.orm.call("res.users", "search_systray_tournaments", [
                query || "",
                80,
                0,
            ]);
            this.state.pickerResults = (data && data.tournaments) || [];
            this.state.pickerTotal = Number((data && data.total) || 0);
        } catch (_e) {
            this.state.pickerResults = [];
            this.state.pickerTotal = 0;
            this.notification.add("Could not load tournaments.", {
                type: "danger",
                title: "Tournament",
            });
        } finally {
            this.state.pickerLoading = false;
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

SaasTournamentSystrayItem.template = "ac_saas_manager.TournamentSystrayItem";

const systray = registry.category("systray");
if (systray.contains("auction.tournament_systray")) {
    systray.remove("auction.tournament_systray");
}
systray.add(
    "auction.tournament_systray",
    { Component: SaasTournamentSystrayItem },
    { sequence: 51 }
);
