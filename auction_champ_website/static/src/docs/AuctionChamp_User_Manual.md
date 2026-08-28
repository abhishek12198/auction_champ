# AuctionChamp User Manual

**Version:** 1.0  
**Document Version:** 1.0  
**Prepared By:** AuctionChamp Team  
**Product Website:** https://www.auctionchamp.live  
**Support Email:** auctionchamp.live@gmail.com  

---

## Copyright Notice

© 2026 AuctionChamp. All Rights Reserved.

This document contains proprietary and confidential information belonging to AuctionChamp. No part of this publication may be reproduced, distributed, transmitted, stored in a retrieval system, or translated into any language in any form or by any means without prior written permission from AuctionChamp.

The software, user interface, workflows, designs, source code, logos, trademarks, and documentation described herein are protected by applicable intellectual property laws.

---

## Revision History

| Version | Date | Author | Description |
|---------|------|--------|-------------|
| 1.0 | July 2026 | AuctionChamp Team | Initial Release |

---

## How to Use This Manual

- **📷 Screenshot placeholders** appear throughout. To show an image on the `/user-manual` web page, save the PNG with the suggested filename under **both**:
  - `docs/screenshots/` (source / checklist)
  - `auction_champ_website/static/src/docs/screenshots/` (what the website actually serves)
  The page auto-replaces matching placeholders with the image; no markdown edit is required.
- Callouts:
  - **Note** — Important information
  - **Tip** — Faster or better ways to work
  - **Warning** — Actions that can affect live auction data
  - **Best Practice** — Recommended operating procedure
- Menu paths use the format: **App / Menu → Submenu → Action**
- Features gated by SaaS plan or security group are marked **(Plan-dependent)** or **(Permission required)**

### Screenshot placeholder format

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE X.Y — Title                                       ║
║  File: docs/screenshots/fig_X_Y_short_name.png               ║
║  Capture: where to go / what to show in the frame            ║
╚══════════════════════════════════════════════════════════════╝
```

---

## Table of Contents

1. [Introduction](#chapter-1--introduction)
2. [About AuctionChamp](#chapter-2--about-auctionchamp)
3. [Why AuctionChamp?](#chapter-3--why-auctionchamp)
4. [System Requirements](#chapter-4--system-requirements)
5. [Getting Started & Navigation](#chapter-5--getting-started--navigation)
6. [User Roles & Permissions](#chapter-6--user-roles--permissions)
7. [SaaS Plans, Accounts & Upgrades](#chapter-7--saas-plans-accounts--upgrades)
8. [Website, Signup & Marketing Pages](#chapter-8--website-signup--marketing-pages)
9. [Tournament Management](#chapter-9--tournament-management)
10. [Team Management](#chapter-10--team-management)
11. [Player Registration & Management](#chapter-11--player-registration--management)
12. [Auction Configuration (Rules Setup)](#chapter-12--auction-configuration-rules-setup)
13. [Player Showcase & Live Auction](#chapter-13--player-showcase--live-auction)
14. [Auctioneer Console](#chapter-14--auctioneer-console)
15. [Owner Console](#chapter-15--owner-console)
16. [Projector Display & Public Live Board](#chapter-16--projector-display--public-live-board)
17. [Payment Tracker & Registration Payments](#chapter-17--payment-tracker--registration-payments)
18. [Reports & Exports](#chapter-18--reports--exports)
19. [WhatsApp & Notifications](#chapter-19--whatsapp--notifications)
20. [Settings & Configuration](#chapter-20--settings--configuration)
21. [Pool Generator](#chapter-21--pool-generator)
22. [FAQs](#chapter-22--faqs)
23. [Troubleshooting](#chapter-23--troubleshooting)
24. [Best Practices](#chapter-24--best-practices)
25. [Glossary](#chapter-25--glossary)
26. [Support](#chapter-26--support)

**Modules covered in this manual:** `auction_module`, `auction_owner`, `auction_auctioneer`, `auction_champ_website`, `ac_saas_manager`, `ac_payment_gateway`, `ac_saas_payment`, `ac_whatsapp`

---

# Chapter 1 – Introduction

## Welcome to AuctionChamp

Welcome to AuctionChamp, a modern cloud-based auction management platform designed to simplify and automate sports player auctions. Whether you're organising a neighbourhood cricket league, a football tournament, or a professional sporting event, AuctionChamp provides an efficient, transparent, and engaging auction experience for organisers, team owners, and participants.

AuctionChamp eliminates the need for manual bidding sheets, spreadsheets, and complex calculations by providing a secure, real-time auction environment. From tournament creation to final player allocation, every stage of the auction lifecycle is managed through a single integrated platform.

The platform is designed with flexibility in mind and supports tournaments of varying sizes, allowing organisers to customise auction rules, budgets, player categories, bidding increments, and team constraints according to their competition requirements.

## Purpose of this Manual

This manual provides comprehensive guidance for using AuctionChamp effectively. It explains every major feature of the platform, describes recommended workflows, and provides step-by-step instructions for performing common tasks.

After reading this manual, users will be able to:

- Create and configure tournaments
- Register and manage players
- Manage participating teams
- Configure auction rules
- Conduct live auctions
- Monitor auction progress
- Generate reports
- Manage tournament settings
- Troubleshoot common issues

## Intended Audience

This document is intended for:

- Tournament Administrators
- Auction Managers / Auctioneers
- League Organisers
- Team Managers / Team Owners
- Tournament Coordinators
- Technical Administrators
- Support Personnel

Some features described in this manual may only be available to users with the appropriate permissions or SaaS plan.

---

# Chapter 2 – About AuctionChamp

## What is AuctionChamp?

AuctionChamp is a Software-as-a-Service (SaaS) platform built to digitise and streamline sports player auctions. It provides a complete ecosystem for organising tournaments, registering players, managing teams, conducting live auctions, and publishing auction results.

Unlike traditional auction processes that rely heavily on spreadsheets and manual calculations, AuctionChamp automates the entire workflow while maintaining transparency, accuracy, and speed.

The platform has been developed using the Odoo framework and follows a modular architecture, enabling organisations to manage multiple tournaments from a single account while ensuring data isolation and security.

## Core Objectives

AuctionChamp aims to:

- Simplify tournament administration
- Eliminate manual auction errors
- Improve transparency during live bidding
- Provide real-time auction tracking
- Reduce administrative overhead
- Enable cloud-based access from anywhere
- Deliver a professional auction experience

## Key Features

### Tournament Management
- Create and manage multiple tournaments
- Tournament branding with logos and themes
- Configure tournament-specific rules
- Control auction lifecycle and registration

### Team Management
- Team registration and logos
- Budget / purse allocation
- Team owner assignment
- Remaining points tracking

### Player Management
- Player registration (self-serve public form)
- Player categorisation by tiers
- Player profile photographs
- Bulk player import (Excel)
- Draft → Auction → Sold / Unsold workflow
- Icon (Key) players

### Live Auction
- Player Showcase (manual Roll Call or Lucky Dip)
- Auctioneer Console (plan-dependent)
- Owner remote bidding (plan-dependent)
- Automatic bid increments via slabs
- Sell / Unsold / Recall workflows
- Mystery players (plan-dependent)
- Auction pause (Break Time)

### Public Display
- Live projector view
- Sponsor / advertiser banners
- Current bid display
- Team balances
- Public Live Bid Board (code-protected)

### Payments & Notifications
- QR / payment-proof registration flow
- Razorpay online registration payment (optional or mandatory)
- Payment Tracker for organisers
- WhatsApp registration confirmation & tournament share
- Email player-card PDF (when configured)

### Reports
- Player cards (PDF / image packs)
- Sold / Unsold Excel export
- Auction Bid Summary / team balance views
- Pool draw & fixture snapshots

---

# Chapter 3 – Why AuctionChamp?

Organising player auctions manually often leads to errors, delays, and disputes. AuctionChamp addresses these challenges through automation and real-time data management.

## Benefits

- Cloud-hosted SaaS platform
- Secure user authentication
- Multi-user access with role-based permissions
- Real-time auction updates
- Automated budget validation
- Transparent bidding process
- Fast report generation
- Mobile-friendly Owner Console
- Centralised tournament management
- Reduced operational effort

---

# Chapter 4 – System Requirements

## Recommended Hardware

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Processor | Dual Core | Quad Core or higher |
| Memory | 4 GB RAM | 8 GB or higher |
| Display | 1366 × 768 | Full HD (1920 × 1080) |
| Internet | 10 Mbps | 25 Mbps or higher |

## Supported Browsers

AuctionChamp supports the latest versions of:

- Google Chrome
- Microsoft Edge
- Mozilla Firefox
- Safari

> **Tip:** For live auctions and the projector screen, use **Google Chrome** or **Microsoft Edge**.

## Network Notes for Auction Day

- Prefer a wired or strong Wi-Fi connection for the auctioneer laptop and projector machine
- Pre-open Player Showcase, Auctioneer Console, and Projector URLs before the event starts
- Keep a backup hotspot ready for mobile Owner Console users

---

# Chapter 5 – Getting Started & Navigation

## 5.1 Logging In

1. Open your AuctionChamp URL (for example `https://www.auctionchamp.live` or your tenant login URL).
2. Enter your **Email / Login** and **Password**.
3. Click **Log in**.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 5.1 — Login Screen                                ║
║  File: docs/screenshots/fig_5_1_login.png                    ║
║  Capture: Full login page with AuctionChamp branding         ║
╚══════════════════════════════════════════════════════════════╝
```

> **Note:** New organisers who purchase a plan from the website receive login credentials by email after successful Razorpay payment (`ac_saas_payment`).

## 5.2 Home Screen / App Switcher

After login you see the AuctionChamp backend home with application icons. Typical root apps for organisers:

| App / Menu | Purpose |
|------------|---------|
| **Tournament(s)** | Create and manage tournaments |
| **Auction Settings** | Teams, players, auction rules, configuration |
| **Player Showcase** | Launch the live auction stage |
| **Auctioneer Console** | Drive bidding live (permission + plan) |
| **Payment Tracker** | Mark player registration payments |
| **Player Dashboard** | Read-only player overview (special role) |
| **SaaS Manager** | Plans, accounts, upgrade requests (platform admin) |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 5.2 — Home / Apps Menu                            ║
║  File: docs/screenshots/fig_5_2_home_apps.png                ║
║  Capture: Backend home showing AuctionChamp app icons        ║
╚══════════════════════════════════════════════════════════════╝
```

## 5.3 Navigation Overview – Auction Settings

**Path:** Auction Settings

| Submenu | Description |
|---------|-------------|
| **Auction → Auction Team(s)** | Per-team purse, players sold, slabs & tier limits |
| **Auction → Auction Rules Setup** | Configure / apply auction rules |
| **Auction → Auction Bid Summary** | Team balance / points table (opens public-style page) |
| **Auction → Public Live Bid Board** | Shareable live board |
| **Auction → Pool Generator** | Create pools and fixtures (plan-dependent) |
| **Players → Draft** | Players not yet in auction |
| **Players → Players in Auction** | Active auction pool |
| **Players → Icon Players** | Key / icon players |
| **Players → Players Sold** | Sold players |
| **Players → Unsold Players** | Unsold players |
| **Players → Unpaid Players** | Players marked unpaid |
| **Players → Players-Jersy** | Jersey details list (permission) |
| **Players → Convert PDF to PNG** | Bulk card image conversion (permission) |
| **Configuration → Team(s)** | Team master |
| **Configuration → Player Tier(s)** | Tier master |
| **Configuration → Website Configurator** | Marketing site content (admin) |
| **Configuration → Website FAQ** | Public FAQ entries (admin) |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 5.3 — Auction Settings Menu Tree                  ║
║  File: docs/screenshots/fig_5_3_auction_settings_menu.png    ║
║  Capture: Expanded Auction Settings sidebar / app menus      ║
╚══════════════════════════════════════════════════════════════╝
```

## 5.4 Working Tournament Switcher (Navbar)

**(SaaS)** Organisers with multiple tournaments use the **tournament switcher** in the top navbar to choose the **working tournament**. Most live screens (Showcase, Live Board, Payment Tracker redirects) use this active tournament.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 5.4 — Tournament Switcher in Navbar               ║
║  File: docs/screenshots/fig_5_4_tournament_systray.png       ║
║  Capture: Navbar dropdown showing tournaments; one marked    ║
║           as active / working                                ║
╚══════════════════════════════════════════════════════════════╝
```

> **Tip:** Always confirm the working tournament before opening Player Showcase on auction day.

## 5.5 Recommended First-Time Setup Sequence

1. Sign up / receive SaaS account credentials  
2. Log in and open **Tournament(s)**  
3. Create tournament (sport, logo, dates, theme)  
4. Add **Teams** and **Player Tiers**  
5. Open registration / upload players  
6. Configure **Auction Rules Setup** (purse, max players, slabs, tier limits)  
7. Assign Auctioneer / Owner users if needed  
8. Test Projector URL + Live Board  
9. Run a short dry-run auction  

---

# Chapter 6 – User Roles & Permissions

AuctionChamp uses Odoo security groups under the **Auction** category (plus SaaS groups).

## 6.1 Role Summary

| Role / Group | Typical User | What they can do |
|--------------|--------------|------------------|
| **Administrator** | Platform / full organiser admin | Full auction access including all sub-roles |
| **User** | Auction operator | Player Showcase, Auction Team(s), core auction actions |
| **Player Setup** | Registration desk | Full player CRUD (Draft, Auction, Icon, Sold, Unsold, Unpaid) |
| **Player Card Print** | Print desk | Print player cards from kanban/form/list |
| **Player Jersey View** | Kit manager | Jersey fields + Players-Jersey menu |
| **PDF to PNG** | Design desk | Convert PDF card sheets to PNG ZIP |
| **Pool Generator** | Fixture planner | Pool Generator access |
| **Bid Board** | Coordinator | Public Live Bid Board |
| **Payment Tracker** | Cash desk | Payment Tracker app (needs Active Tournament) |
| **Player Dashboard Viewer** | Observer | Player Detail Dashboard only |
| **Team Owner** / **Owner** | Franchise owner | Owner Console bidding for assigned team |
| **Auctioneer** | Auctioneer | Auctioneer Console |
| **SaaS Account User** | Paying organiser | Own tournaments within plan limits |
| **SaaS Manager** | AuctionChamp ops | All SaaS accounts, plans, upgrade approvals |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 6.1 — User Form with Auction Access Rights        ║
║  File: docs/screenshots/fig_6_1_user_groups.png              ║
║  Capture: Settings → Users → Access Rights showing Auction   ║
║           and SaaS groups                                    ║
╚══════════════════════════════════════════════════════════════╝
```

## 6.2 Assigning a Team Owner

1. Create or open the **User**.
2. Grant **Owner** / **Team Owner** group.
3. Set the user’s **Tournament** and **Team** (Owner Console uses these assignments).
4. Ask the owner to open `/auction/owner/console` after login.

> **Warning:** Owners must be linked to the correct team before live bidding. Wrong assignment places bids for the wrong franchise.

## 6.3 Assigning an Auctioneer

1. Grant the **Auctioneer** group (Administrators imply this automatically).
2. Ensure Auctioneer Console is allowed on the organiser’s **SaaS plan** (Classic and above).
3. Open **Auctioneer Console** from the app menu or `/auction/auctioneer/console`.

---

# Chapter 7 – SaaS Plans, Accounts & Upgrades

**Modules:** `ac_saas_manager`, `ac_saas_payment`

## 7.1 Purpose

SaaS Manager enforces plan limits and feature gates for organiser accounts:

- Max tournaments, teams per tournament, players per tournament
- Feature flags: Random mode, Auctioneer Console, Owner bidding, Pool Creator, Parallel sessions, Mystery players, allowed card themes

## 7.2 Plan Comparison (Default Catalogue)

| Feature | Standard | Classic | Pro | Pro+ |
|---------|----------|---------|-----|------|
| Max tournaments | 5 | 6 | 10 | 16 |
| Max teams / tournament | 6 | 8 | 12 | 24 |
| Max players / tournament | 80 | 100 | 150 | 300 |
| Lucky Dip (Random) | No | Yes | Yes | Yes |
| Auctioneer Console | No | Yes | Yes | Yes |
| Owners remote bidding | No | No | Yes | Yes |
| Pool Creator | No | No | Yes | Yes |
| Parallel multi-device sessions | No | No | Yes | Yes |
| Mystery players | No | No | Yes | Yes |
| Default card themes | Lemon | Vanilla | Strawberry | Strawberry, Cherry, Pistah |
| Notes | Mini / friendly | Mini + auctioneer | Premier leagues | Large premier; contact support beyond |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 7.1 — Website Pricing Cards                       ║
║  File: docs/screenshots/fig_7_1_pricing_plans.png            ║
║  Capture: Homepage Plans & Pricing section                   ║
╚══════════════════════════════════════════════════════════════╝
```

## 7.3 SaaS Account (Organiser View)

Organisers see their own account usage (tournaments / teams / players) against plan limits. When a limit is hit, creation is blocked with an upgrade hint.

**Account states** typically include Active / Expired (and related operational states managed by SaaS Manager).

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 7.2 — SaaS Account Form (Organiser)               ║
║  File: docs/screenshots/fig_7_2_saas_account.png             ║
║  Capture: Account with plan, dates, usage counters           ║
╚══════════════════════════════════════════════════════════════╝
```

## 7.4 SaaS Manager (Platform Admin)

**Path:** SaaS Manager → Accounts / Plans / Upgrade Requests

### Accounts
- Link **Login User**, **Plan**, **Start Date**, **End Date**
- Review usage and freeze/expire handling

### Plans
- Configure limits and feature toggles listed above
- Set website pricing display fields (list price, validity days, etc.)

### Upgrade Requests
- Organisers submit upgrade requests from the app
- With `ac_saas_payment` enabled, upgrades can be **paid via Razorpay** (prorated) using **Pay & upgrade**
- Managers can also approve manually where payment is not required

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 7.3 — Upgrade Request with Payment Summary        ║
║  File: docs/screenshots/fig_7_3_upgrade_request.png          ║
║  Capture: New plan price, prorated credit, amount to pay     ║
╚══════════════════════════════════════════════════════════════╝
```

## 7.5 Paying for an Upgrade (Organiser)

1. Open your upgrade / plan screen and choose the target plan.
2. Review **Amount to pay** (proration shown when applicable).
3. Click **Pay & upgrade**.
4. Complete Razorpay checkout.
5. After verification, the account plan updates and gated features unlock.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 7.4 — SaaS Upgrade Razorpay Checkout              ║
║  File: docs/screenshots/fig_7_4_upgrade_checkout.png         ║
║  Capture: Upgrade payment page before / during Razorpay      ║
╚══════════════════════════════════════════════════════════════╝
```

> **Note:** If an account is frozen or expired, live auction screens may show a blocking page until renewal.

---

# Chapter 8 – Website, Signup & Marketing Pages

**Modules:** `auction_champ_website`, `ac_saas_payment`

## 8.1 Public Pages

| URL | Purpose |
|-----|---------|
| `/` | Marketing homepage (hero, features, pricing, FAQ, live tournaments) |
| `/privacy-policy` | Privacy policy |
| `/terms-and-conditions` | Terms & conditions |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 8.1 — AuctionChamp Homepage Hero                  ║
║  File: docs/screenshots/fig_8_1_homepage_hero.png            ║
║  Capture: First viewport of public homepage                  ║
╚══════════════════════════════════════════════════════════════╝
```

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 8.2 — Plans & Pricing / Get Started               ║
║  File: docs/screenshots/fig_8_2_get_started.png              ║
║  Capture: Pricing section with Get Started CTA               ║
╚══════════════════════════════════════════════════════════════╝
```

## 8.2 Website Signup Flow (Paid)

1. Visitor selects a plan and clicks **Get Started**.
2. Enters signup details (name, email, phone, etc. as shown on the form).
3. Pays via Razorpay.
4. System creates the SaaS account + login user.
5. Credentials are emailed; visitor lands on the success / done page.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 8.3 — Signup Form                                 ║
║  File: docs/screenshots/fig_8_3_signup_form.png              ║
║  Capture: Website plan signup form                           ║
╚══════════════════════════════════════════════════════════════╝
```

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 8.4 — Signup Payment Success                      ║
║  File: docs/screenshots/fig_8_4_signup_done.png              ║
║  Capture: Post-payment confirmation / credentials notice     ║
╚══════════════════════════════════════════════════════════════╝
```

## 8.3 Website Configurator (Admin)

**Path:** Auction Settings → Configuration → Website Configurator

Edit marketing content: hero, features, testimonials, pricing display flags, footer, etc.

**Path:** Auction Settings → Configuration → Website FAQ

Maintain FAQ Q&A shown on the public site.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 8.5 — Website Configurator Form                   ║
║  File: docs/screenshots/fig_8_5_website_config.png           ║
║  Capture: Backend Website Configurator                       ║
╚══════════════════════════════════════════════════════════════╝
```

---

# Chapter 9 – Tournament Management

**Module:** `auction_module` (+ SaaS inheritance)

## 9.1 Purpose

A **Tournament** is the top-level container for teams, players, auction rules, registration, projector branding, and live session state.

## 9.2 Navigation

- **SaaS organisers:** Tournament(s) (own tournaments only)  
- **Administrators:** Tournament(s) (all)

## 9.3 Creating a Tournament

1. Open **Tournament(s)** → **Create**.
2. Fill **Tournament Info**:
   - **Name** (required)
   - **Short Description** (required)
   - **Game / Sport:** Cricket or Football (Kabaddi is listed as Coming Soon)
   - **Tournament Dates**
   - **Logo**
   - **Organizer Name / Contact**
3. Choose **Player Call-Up Mode**:
   - **Roll Call** — manual / dice number selection
   - **Lucky Dip** — random next player **(Plan-dependent)**
4. Choose **Theme** (player card / showcase skin; options limited by plan).
5. Save.

A unique **Tournament Code** (format `AC#` + digits) and **URL Slug** are generated automatically.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 9.1 — Create Tournament Form (Header)             ║
║  File: docs/screenshots/fig_9_1_tournament_create.png        ║
║  Capture: New tournament form with Name, Sport, Logo         ║
╚══════════════════════════════════════════════════════════════╝
```

## 9.4 Tournament Form – Header Actions

| Button | Purpose |
|--------|---------|
| **Set Auction Rules** | Opens Auction Rules Setup wizard |
| **Auction Rules** | Opens existing rules |
| **Export Sold / Unsold** | Excel export of sold & unsold players |
| **Deactivate Tournament** | Soft-deactivate |
| **Remove Duplicates** | Clean duplicate player records |
| **Open / Close Registration** | Toggle public registration |
| **Enable / Disable Live Board** | Toggle public live board stream |
| **Open Registration Link** | Opens share URL |
| **Payment Tracker** | Opens tracker for this tournament |
| **Clear Stage** | Clears current on-stage player |
| **Clear Auction History** | Clears history **(Warning)** |
| **Share on WhatsApp** | Invite wizard (`ac_whatsapp`) |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 9.2 — Tournament Form Status Buttons              ║
║  File: docs/screenshots/fig_9_2_tournament_actions.png       ║
║  Capture: Header buttons + registration/live board toggles   ║
╚══════════════════════════════════════════════════════════════╝
```

## 9.5 Tournament Tabs

### Players
- Inline player list
- **Upload Players** (Excel wizard)

### Teams & Tiers
- Team list with logos
- Tier list (DEFAULT tier is created automatically)
- **Upload Teams & Tiers**

### Other Attributes *(Football only)*
- Define Att-Labels used on cards and Excel upload columns

### Presentation & Theme
- Card theme
- **Sold Screen Duration (seconds)**
- **Next Player Countdown (seconds)**
- **Quick-Select Points** (comma-separated sell modal presets)
- **Unmask Player Contact?** (requires privacy agreement)
- **Jersey Included?**
- Player self-registration links & limits
- Projector URL section

### Poster & Payment Images
- Tournament poster
- Payment QR / scanner
- Payment instructions text

### Venue
- Tournament venue
- Auction date & auction venue (shown on projector)

### Rules & Regulations
- HTML rules text for display / sharing

### Advertisers
- Sponsor name + banner/logo for projector / boards

### Pools and Fixtures
- Download saved pool draw / fixture snapshots

### Online Registration Payment (Razorpay) — `ac_payment_gateway`
- **Include Registration Payment**
- **Payment Requirement:** Optional / Mandatory
- **Registration Currency** & **Registration Fee**

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 9.3 — Presentation & Theme Tab                    ║
║  File: docs/screenshots/fig_9_3_presentation_theme.png       ║
║  Capture: Theme + timing + registration URL fields           ║
╚══════════════════════════════════════════════════════════════╝
```

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 9.4 — Razorpay Registration Payment Settings      ║
║  File: docs/screenshots/fig_9_4_registration_payment.png     ║
║  Capture: Include Registration Payment + fee fields          ║
╚══════════════════════════════════════════════════════════════╝
```

## 9.6 Registration URL Format

`{base_url}/{database}/{tournament_slug}/player/register`

Share this link for player self-registration.

## 9.7 Field Reference (Selected)

| Field | Description |
|-------|-------------|
| Max points alloted for a team | Default purse reference |
| Max registrations | Cap public registrations (0 = no cap UI behaviour per form) |
| WhatsApp Group Link | Shown on registration success |
| Live Board Active | Public board online/offline |
| Break Time | Shows break screen on live board |
| Auction declared complete | Marks auction finished for displays |

> **Best Practice:** Complete Teams, Tiers, Themes, Poster, and Payment setup **before** opening registration.

---

# Chapter 10 – Team Management

## 10.1 Purpose

Teams (franchises) bid using a purse (points). Each team appears on Auction Team(s), Owner Console, projector, and balance boards.

## 10.2 Navigation

**Path:** Auction Settings → Configuration → Team(s)  
Also editable from Tournament → **Teams & Tiers**.

## 10.3 Creating a Team

1. Open Team(s) → Create (or add from tournament).
2. Enter:
   - **Team Name** (required)
   - **Team Logo**
   - **Owner** (manager name display)
   - **Tournament**
3. Save.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 10.1 — Team Form                                  ║
║  File: docs/screenshots/fig_10_1_team_form.png               ║
║  Capture: Team name, logo, owner fields                      ║
╚══════════════════════════════════════════════════════════════╝
```

## 10.4 Bulk Upload Teams & Tiers

From the tournament form click **Upload Teams & Tiers**, download the template if provided by the wizard, fill rows, and upload.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 10.2 — Upload Teams & Tiers Wizard                ║
║  File: docs/screenshots/fig_10_2_upload_teams.png            ║
║  Capture: Upload wizard dialog                               ║
╚══════════════════════════════════════════════════════════════╝
```

## 10.5 Auction Team(s) Screen

**Path:** Auction Settings → Auction → Auction Team(s)

Shows each team’s auction purse configuration after rules are applied:

- Total points / remaining points
- Max players
- Players purchased
- Bid slabs & tier limits (via rules)

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 10.3 — Auction Team(s) List / Kanban              ║
║  File: docs/screenshots/fig_10_3_auction_teams.png           ║
║  Capture: Teams with remaining points visible                ║
╚══════════════════════════════════════════════════════════════╝
```

> **Warning:** Changing purse mid-auction can invalidate ongoing bids. Prefer finalising rules before going live.

---

# Chapter 11 – Player Registration & Management

## 11.1 Player Lifecycle States

| State | Meaning |
|-------|---------|
| **Draft** | Registered / entered but not in the live auction pool |
| **In Auction** | Available to be called on stage |
| **Sold** | Purchased by a team |
| **Unsold** | Passed; can be brought back later |
| **Icon / Key Player** | Special sold/icon designation (Icon Players menu) |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 11.1 — Players Menu States                        ║
║  File: docs/screenshots/fig_11_1_players_menus.png           ║
║  Capture: Draft / In Auction / Sold / Unsold menus           ║
╚══════════════════════════════════════════════════════════════╝
```

## 11.2 Public Player Registration

1. Open Registration (tournament must have **Registration Open**).
2. Player fills:
   - **Player Photo** (required)
   - **Full Name** (required)
   - Sport-specific fields (Role / batting-bowling for cricket; position / foot for football)
   - **Player Tier** (required when tiers are offered)
   - **Mobile Number** (required)
   - Optional: blood group, address, previous club, jersey fields (if enabled)
   - Payment proof upload **or** Razorpay checkout (if online payment enabled)
3. On success, player may download **Player Card PDF** and **Instagram Card JPG**, and join WhatsApp group if configured.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 11.2 — Public Registration Form                   ║
║  File: docs/screenshots/fig_11_2_registration_form.png       ║
║  Capture: Full registration page with poster sidebar         ║
╚══════════════════════════════════════════════════════════════╝
```

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 11.3 — Registration Success Screen                ║
║  File: docs/screenshots/fig_11_3_registration_success.png    ║
║  Capture: Success + download buttons + WhatsApp join         ║
╚══════════════════════════════════════════════════════════════╝
```

### Payment modes on registration

| Mode | Behaviour |
|------|-----------|
| QR / proof (default) | Player uploads payment screenshot; organiser marks paid in Payment Tracker |
| Razorpay **Optional** | Player can register now and pay later via checkout link |
| Razorpay **Mandatory** | Player record is created only after successful payment |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 11.4 — Razorpay Registration Checkout             ║
║  File: docs/screenshots/fig_11_4_reg_razorpay.png            ║
║  Capture: Registration payment checkout page                 ║
╚══════════════════════════════════════════════════════════════╝
```

## 11.3 Creating Players Manually (Backend)

**Path:** Auction Settings → Players → Draft → Create

Key fields:

- Name, Photo, Contact, Tier, Role / attributes
- **Payment Received**
- Jersey details (if group enabled)
- Mystery player flag **(Plan-dependent)**

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 11.5 — Player Profile Form                        ║
║  File: docs/screenshots/fig_11_5_player_form.png             ║
║  Capture: Player Profile with photo and category             ║
╚══════════════════════════════════════════════════════════════╝
```

## 11.4 Bulk Upload Players

From Tournament → Players tab → **Upload Players**.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 11.6 — Upload Players Wizard                      ║
║  File: docs/screenshots/fig_11_6_upload_players.png          ║
║  Capture: Excel upload dialog                                ║
╚══════════════════════════════════════════════════════════════╝
```

## 11.5 Moving Players Into Auction

From Draft (or via bulk actions / wizards):

- Move selected players to **In Auction**
- Use **Bring to Auction** on Unsold players

## 11.6 Player Actions by State

| Action | When available |
|--------|----------------|
| **Sell to Team** | In Auction |
| **Set to Unsold** | In Auction |
| **Bring to Auction** | Unsold |
| **Set as Icon Player** | Eligible sold flow |
| **Revoke Icon Player** | Icon players |
| **Recall to Auction** | Sold (non-icon) |
| **Print** | Card print permission |
| **Send WhatsApp confirm** | `ac_whatsapp` |
| **Email card PDF** | `ac_whatsapp` / mail configured |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 11.7 — Player List Action Buttons                 ║
║  File: docs/screenshots/fig_11_7_player_actions.png          ║
║  Capture: List/kanban showing Sell / Unsold / Recall         ║
╚══════════════════════════════════════════════════════════════╝
```

## 11.7 Icon (Key) Players

Use **Set as Icon Player** wizard to assign a player as a franchise icon with points/team as required by your event rules. Icon players appear under **Players → Icon Players**.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 11.8 — Set as Icon Player Wizard                  ║
║  File: docs/screenshots/fig_11_8_icon_player_wizard.png      ║
║  Capture: Icon player wizard dialog                          ║
╚══════════════════════════════════════════════════════════════╝
```

## 11.8 Mystery Players *(Pro / Pro+)*

Mark a player as mystery so the public display hides identity until the auctioneer **reveals** the player from the Auctioneer Console.

> **Note:** Feature availability is enforced by the SaaS plan (`allow_mystery_players`).

---

# Chapter 12 – Auction Configuration (Rules Setup)

## 12.1 Purpose

**Auction Rules Setup** defines purse, squad size, bid increment slabs, and per-tier recruitment limits for every team.

**Path:** Auction Settings → Auction → Auction Rules Setup  
Or Tournament → **Set Auction Rules**

## 12.2 Procedure

1. Open Auction Rules Setup.
2. Set:
   - **Total Purse Value** (`max_points`)
   - **Max no of players**
3. Review **Teams** included.
4. Configure **Slab Setup**:
   - **From** / **To** amount ranges
   - **Increment** for that range
5. Configure **Tier Limits**:
   - Tier
   - **Max Players per Team**
   - **Base Point** (0 = use global base)
   - **Max Call for a Player** (0 = unlimited)
6. Click **Apply** and confirm.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 12.1 — Auction Rules Setup Wizard                 ║
║  File: docs/screenshots/fig_12_1_auction_rules.png           ║
║  Capture: Purse, slabs, tier limits filled                   ║
╚══════════════════════════════════════════════════════════════╝
```

> **Warning:** Applying rules starts / refreshes the auction process for teams. Confirm values carefully before auction day.

## 12.3 Example Bid Slab

| From | To | Increment |
|------|----|-----------|
| 0 | 1000 | 50 |
| 1001 | 5000 | 100 |
| 5001 | 20000 | 250 |

## 12.4 Validation Concepts

- Bids cannot exceed a team’s **remaining points** while still leaving enough purse for remaining mandatory slots (system calculates max call / remaining players constraints).
- Tier limits prevent over-recruiting a category.

> **Best Practice:** Print or screenshot the final rules and share with owners before the auction starts.

---

# Chapter 13 – Player Showcase & Live Auction

## 13.1 Purpose

**Player Showcase** is the primary stage controller for calling players, selling, marking unsold, and driving the projector.

**Path:** Player Showcase app → `/auction/showcase`  
(Requires auction rules to be ready; otherwise a rules-required page is shown.)

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 13.1 — Auction Rules Required Screen              ║
║  File: docs/screenshots/fig_13_1_rules_required.png          ║
║  Capture: Blocking page when rules not set                   ║
╚══════════════════════════════════════════════════════════════╝
```

## 13.2 Opening Showcase

1. Select the correct working tournament in the navbar.
2. Open **Player Showcase**.
3. Confirm projector URL is open on the display machine.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 13.2 — Player Showcase Main Screen                ║
║  File: docs/screenshots/fig_13_2_showcase.png                ║
║  Capture: Showcase with player queue / on-stage area         ║
╚══════════════════════════════════════════════════════════════╝
```

## 13.3 Call-Up Modes

### Roll Call
- Pick a player from the list, or use dice / squad number flow synced to the projector.

### Lucky Dip *(plan-dependent)*
- System draws the next player randomly (**Next Player** style flow).

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 13.3 — Dice / Number Call-Up                      ║
║  File: docs/screenshots/fig_13_3_dice_callup.png             ║
║  Capture: Dice animation / number selection on showcase      ║
╚══════════════════════════════════════════════════════════════╝
```

## 13.4 On-Stage Workflow

1. Bring player on stage (`is_on_stage`).
2. Announce base price / start bidding (via Auctioneer Console or manual sell).
3. Finalise:
   - **Sell** → choose team + points (quick-select points available)
   - **Unsold** → mark passed
4. Sold celebration screen displays for **Sold Screen Duration**.
5. Next-player countdown overlay may appear before the following call-up.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 13.4 — Sell Player Modal                          ║
║  File: docs/screenshots/fig_13_4_sell_modal.png              ║
║  Capture: Sell modal with team + points + quick selects      ║
╚══════════════════════════════════════════════════════════════╝
```

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 13.5 — Sold Celebration Overlay                   ║
║  File: docs/screenshots/fig_13_5_sold_stamp.png              ║
║  Capture: SOLD stamp / celebration on projector or showcase  ║
╚══════════════════════════════════════════════════════════════╝
```

## 13.5 Break Time

Enable **Break Time** on the tournament (or via live controls where available) to show a break holding screen on the live board / projector flow.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 13.6 — Break Time Screen                          ║
║  File: docs/screenshots/fig_13_6_break_time.png              ║
║  Capture: Break Time public display                          ║
╚══════════════════════════════════════════════════════════════╝
```

## 13.6 Corrections

- **Recall to Auction** for wrongly sold players
- Sale correction endpoints / UI allow updating sold team/points when authorised
- **Clear Stage** if the wrong player is showing

> **Warning:** Correct during a pause; announce the correction publicly to avoid owner disputes.

---

# Chapter 14 – Auctioneer Console

**Module:** `auction_auctioneer`  
**Permission:** Auctioneer group  
**Plan:** Classic and above (`allow_auctioneer_console`)

## 14.1 Purpose

Full-screen console (no standard Odoo chrome) for the auctioneer to:

- Drive showcase flow (Manual dice/numbers or Random Next Player)
- See all teams and purse balances
- See current player on stage
- Place / increment bids per team
- Reset bid, mark unsold, finalize sale
- Reveal mystery players
- Correct a bid amount

**URLs:**
- `/auction/auctioneer/console` (redirects to active tournament)
- `/auction/auctioneer/console/<tournament_slug>`

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 14.1 — Auctioneer Console Overview                ║
║  File: docs/screenshots/fig_14_1_auctioneer_console.png      ║
║  Capture: Full console with teams grid + on-stage player     ║
╚══════════════════════════════════════════════════════════════╝
```

## 14.2 Typical Bidding Flow

1. Call / next player so the player is on stage (synced to projector).
2. Click a **team** button.
3. Confirm / adjust bid in the bid modal (increment follows slabs).
4. Continue until hammer time.
5. **Finalize** the sale (or **Mark Unsold**).
6. Proceed to next player.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 14.2 — Place Bid Modal                            ║
║  File: docs/screenshots/fig_14_2_place_bid_modal.png         ║
║  Capture: Bid modal for a selected team                      ║
╚══════════════════════════════════════════════════════════════╝
```

## 14.3 Console Actions Reference

| Action | Effect |
|--------|--------|
| Dice / Call Player | Puts selected player on stage |
| Next Player | Random/linear advance per mode |
| Reveal Mystery | Unmasks mystery player |
| Place Bid | Sets current bid for team |
| Reset Bid | Clears current bid state |
| Mark Unsold | Player → Unsold |
| Finalize Bid | Completes sale to leading team |
| Correct Bid | Adjusts locked/current bid value |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 14.3 — Mystery Reveal Control                     ║
║  File: docs/screenshots/fig_14_3_mystery_reveal.png          ║
║  Capture: Mystery player pending reveal UI                   ║
╚══════════════════════════════════════════════════════════════╝
```

> **Tip:** Run Auctioneer Console on a dedicated laptop; keep Player Showcase/projector on the display PC.

---

# Chapter 15 – Owner Console

**Module:** `auction_owner`  
**Permission:** Owner group + team assignment  
**Plan:** Pro / Pro+ (`allow_owner_bidding`)

## 15.1 Purpose

Mobile-friendly dashboard for franchise owners to:

- Watch the live auction
- See purse balance and squad
- Place bids for their assigned team
- Revoke their own bid when rules allow

**URL:** `/auction/owner/console`  
Owners landing on `/web` may be redirected straight to the Owner Console.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 15.1 — Owner Console (Mobile)                     ║
║  File: docs/screenshots/fig_15_1_owner_console_mobile.png    ║
║  Capture: Phone-width view with player + Bid button          ║
╚══════════════════════════════════════════════════════════════╝
```

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 15.2 — Owner Console (Desktop)                    ║
║  File: docs/screenshots/fig_15_2_owner_console_desktop.png   ║
║  Capture: Desktop owner dashboard with squad list            ║
╚══════════════════════════════════════════════════════════════╝
```

## 15.2 Placing a Bid

1. Wait until a player is on stage and bidding is open.
2. Tap **Bid** / place bid at the offered amount (next increment).
3. Confirm success toast / UI state.
4. Use **Revoke** only if your bid is still eligible to withdraw.

> **Warning:** Budget validation applies. If the bid would break remaining-players purse rules, it is rejected.

## 15.3 Counter / Live Bid Helpers

Public helper endpoints support counter checks and live bid polling used by the console UI. Owners should refresh if the connection drops; re-login if session expires.

---

# Chapter 16 – Projector Display & Public Live Board

## 16.1 Projector Display

Each tournament exposes a **Projector URL** (after auction rules exist):

`{base}/{db}/{slug}/...` (open via tournament **Projector URL** field / Share URL)

Shows:

- Current player / mystery state
- Current bid & leading team
- Team balances
- Advertiser banners
- Sold / Unsold stamps
- Optional pool draw / fixtures board modes

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 16.1 — Projector Live Player Screen               ║
║  File: docs/screenshots/fig_16_1_projector_player.png        ║
║  Capture: Full-bleed projector with player + bid             ║
╚══════════════════════════════════════════════════════════════╝
```

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 16.2 — Projector with Sponsor Banner              ║
║  File: docs/screenshots/fig_16_2_projector_sponsor.png       ║
║  Capture: Advertiser banner visible on projector             ║
╚══════════════════════════════════════════════════════════════╝
```

### Projector Board Modes

| Mode | Use |
|------|-----|
| Hidden (idle) | Normal auction player flow |
| Pool Draw | Show saved pools |
| Fixtures | Show fixture schedule |

## 16.2 Public Live Bid Board

**Path:** Auction Settings → Auction → Public Live Bid Board  
**Shortcut:** `/auction/my/live-board` (uses working tournament)

- Must be **Live Board Active** on the tournament
- May require **Tournament Code** unlock for public viewers

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 16.3 — Live Board Unlock Screen                   ║
║  File: docs/screenshots/fig_16_3_live_board_unlock.png       ║
║  Capture: Code entry unlock page                             ║
╚══════════════════════════════════════════════════════════════╝
```

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 16.4 — Public Live Bid Board                      ║
║  File: docs/screenshots/fig_16_4_live_board.png              ║
║  Capture: Live board with current bid + balances             ║
╚══════════════════════════════════════════════════════════════╝
```

## 16.3 Auction Bid Summary / Team Balance

**Path:** Auction → Auction Bid Summary  
Opens the team balance / points table view for sharing with stakeholders.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 16.5 — Team Balance / Points Table                ║
║  File: docs/screenshots/fig_16_5_team_balance.png            ║
║  Capture: All teams remaining points & player counts         ║
╚══════════════════════════════════════════════════════════════╝
```

---

# Chapter 17 – Payment Tracker & Registration Payments

## 17.1 Payment Tracker

**Path:** Payment Tracker app (root menu)  
**Permission:** Auction group or **Payment Tracker** role + Active Tournament

Use cases:

- See registered players for the tournament
- Mark / unmark **Payment Received**
- Support cash desk on registration day

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 17.1 — Payment Tracker Screen                     ║
║  File: docs/screenshots/fig_17_1_payment_tracker.png         ║
║  Capture: Player list with paid/unpaid toggles               ║
╚══════════════════════════════════════════════════════════════╝
```

## 17.2 Unpaid Players Menu

**Path:** Auction Settings → Players → Unpaid Players  
Filters players with payment not received for follow-up.

## 17.3 Razorpay System Configuration (Admin)

**Path:** Settings → Razorpay Payment Gateway (`ac_payment_gateway`)

Configure:

- Razorpay Key ID
- Razorpay Key Secret
- Razorpay Webhook Secret (if used)

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 17.2 — Razorpay Settings                          ║
║  File: docs/screenshots/fig_17_2_razorpay_settings.png       ║
║  Capture: Settings block with Key ID fields (mask secrets)   ║
╚══════════════════════════════════════════════════════════════╝
```

> **Warning:** Never publish Key Secret in the user manual screenshots. Mask secrets before capture.

## 17.4 SaaS Upgrade Payment Settings

**Path:** Settings → SaaS Plan Upgrades (`ac_saas_payment`)

Enables paid upgrades and website signup checkout behaviour tied to the same Razorpay credentials / SaaS payment sequences.

---

# Chapter 18 – Reports & Exports

## 18.1 Player Cards

- Print from player kanban/form/list (**Player Card Print** permission)
- Theme follows tournament **Theme** (Lemon, Vanilla, Butterscotch, Strawberry, Cherry, Pistah, Blackberry, Football variants)
- Bulk image download via Players Card URL action where enabled
- **Convert PDF to PNG** wizard for sheet-to-image packs

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 18.1 — Printed Player Card Sample                 ║
║  File: docs/screenshots/fig_18_1_player_card.png             ║
║  Capture: Sample PDF/card for one player                     ║
╚══════════════════════════════════════════════════════════════╝
```

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 18.2 — Convert PDF to PNG Wizard                  ║
║  File: docs/screenshots/fig_18_2_pdf_to_png.png              ║
║  Capture: Upload PDF → download ZIP flow                     ║
╚══════════════════════════════════════════════════════════════╝
```

## 18.2 Export Sold / Unsold

From Tournament → **Export Sold / Unsold** to download Excel for settlement and notices.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 18.3 — Export Sold / Unsold Result                ║
║  File: docs/screenshots/fig_18_3_export_sold_unsold.png      ║
║  Capture: Excel open or download toast                       ║
╚══════════════════════════════════════════════════════════════╝
```

## 18.3 Auction History

Administrators can access **Auction History** under technical menus for audit of bidding events.

## 18.4 Pool / Fixture Snapshots

From Tournament → Pools and Fixtures, download PNG snapshots generated by Pool Generator.

---

# Chapter 19 – WhatsApp & Notifications

**Module:** `ac_whatsapp`

## 19.1 System Configuration (Admin)

**Path:** Settings → WhatsApp

| Setting | Purpose |
|---------|---------|
| WhatsApp Provider | Twilio or Meta |
| Twilio Account SID / Auth Token / From | Twilio WhatsApp sender |
| Registration Content SID | Twilio content template for registration confirm |
| Registration Content Variables (JSON) | Template variable mapping |
| Inbound auto-reply text | Auto-reply for Twilio webhook `/ac_whatsapp/twilio/reply` |
| Meta Access Token / Phone Number ID / WABA ID | Meta Cloud API |
| Default country code | e.g. 91 |
| Auto-send registration WhatsApp | Send confirm automatically after register |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 19.1 — WhatsApp Settings                          ║
║  File: docs/screenshots/fig_19_1_whatsapp_settings.png       ║
║  Capture: Provider + Twilio/Meta fields (mask tokens)        ║
╚══════════════════════════════════════════════════════════════╝
```

## 19.2 Share Tournament on WhatsApp

From Tournament form → **Share on WhatsApp**:

1. Enter recipient mobile numbers.
2. Edit message caption (poster image used when API send is available).
3. **Send via WhatsApp API** or **Open WhatsApp Web (text only)**.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 19.2 — Share on WhatsApp Wizard                   ║
║  File: docs/screenshots/fig_19_2_share_whatsapp.png          ║
║  Capture: Wizard with numbers + caption                      ║
╚══════════════════════════════════════════════════════════════╝
```

## 19.3 Player Confirmation Actions

On a player form:

- **Send WhatsApp confirm**
- **Email card PDF**

Tracks flags such as **Registration Confirm Sent** / **Registration WhatsApp Sent**.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 19.3 — Player WhatsApp / Email Buttons            ║
║  File: docs/screenshots/fig_19_3_player_notify_buttons.png   ║
║  Capture: Player form header notify buttons                  ║
╚══════════════════════════════════════════════════════════════╝
```

## 19.4 Registration Success WhatsApp Group

Set **WhatsApp Group Link** on the tournament so successful registrants can join the community group from the success page.

---

# Chapter 20 – Settings & Configuration

## 20.1 Organiser Configuration Checklist

| Area | Where |
|------|-------|
| Teams | Configuration → Team(s) |
| Tiers | Configuration → Player Tier(s) |
| Auction rules | Auction → Auction Rules Setup |
| Theme / timing | Tournament → Presentation & Theme |
| Registration | Tournament toggles + Poster & Payment |
| Online fee | Tournament Razorpay section |
| Live board | Enable Live Board + share code |
| Owners / Auctioneer | Users → Access Rights + team link |
| Website content | Configuration → Website Configurator (admin) |

## 20.2 Player Tiers

Create tiers such as DEFAULT, A, B, Icon categories. Tier limits in auction rules reference these records.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 20.1 — Player Tier Form                           ║
║  File: docs/screenshots/fig_20_1_player_tier.png             ║
║  Capture: Tier name + color                                  ║
╚══════════════════════════════════════════════════════════════╝
```

## 20.3 Contact Privacy

To show full mobile numbers on cards/displays:

1. Open Tournament → Presentation & Theme → Player Contact.
2. Click **Agree & Unmask Contacts** and accept the privacy wizard.
3. Use **Remask Contacts** to hide numbers again.

Agreement user, timestamp, and policy version are stored.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 20.2 — Expose Contact Privacy Wizard              ║
║  File: docs/screenshots/fig_20_2_contact_privacy.png         ║
║  Capture: Privacy agreement dialog                           ║
╚══════════════════════════════════════════════════════════════╝
```

---

# Chapter 21 – Pool Generator

**Path:** Auction Settings → Auction → Pool Generator  
**Permission / Plan:** Pool Generator group + plan flag `allow_pool_creator` (Pro+)

## 21.1 Purpose

Assign teams into pools and generate fixture schedules for projector display and downloads.

## 21.2 High-Level Steps

1. Open Pool Generator for the working tournament.
2. Configure pools / assign teams.
3. Generate fixtures as needed.
4. Save — snapshots appear on Tournament → Pools and Fixtures.
5. Switch projector board mode to Pool Draw or Fixtures when presenting.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 21.1 — Pool Generator Screen                      ║
║  File: docs/screenshots/fig_21_1_pool_generator.png          ║
║  Capture: Pool assignment UI                                 ║
╚══════════════════════════════════════════════════════════════╝
```

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 21.2 — Projector Pool Draw Board                  ║
║  File: docs/screenshots/fig_21_2_projector_pools.png         ║
║  Capture: Projector showing pools                            ║
╚══════════════════════════════════════════════════════════════╝
```

> **Note:** Opening Player Showcase / putting a player on stage clears projector board mode so the auction player view returns.

---

# Chapter 22 – FAQs

**Q1. I cannot open Player Showcase.**  
Ensure auction rules are applied and your SaaS account is active (not frozen/expired). Confirm working tournament.

**Q2. Lucky Dip / Random is missing.**  
Your plan may not allow random mode (Standard). Upgrade to Classic or higher.

**Q3. Auctioneer Console menu is missing.**  
Need **Auctioneer** (or Administrator) rights and a plan that allows Auctioneer Console.

**Q4. Owners cannot bid.**  
Need Pro/Pro+ plan, Owner group, correct team assignment, and owner bidding enabled on plan.

**Q5. Registration link shows closed.**  
Click **Open Registration** on the tournament.

**Q6. Live board shows offline.**  
Enable **Live Board Active**. Viewers may also need the tournament code.

**Q7. Razorpay payment succeeded but player missing (Mandatory mode).**  
Check payment verification page/logs; ensure webhook/keys are correct. Contact support with payment reference.

**Q8. WhatsApp confirm not sending.**  
Verify provider credentials, Content SID, and player mobile with country code.

**Q9. Why are contacts masked?**  
By design. Unmask only after accepting the privacy agreement.

**Q10. Can I run two tournaments on two devices?**  
Parallel sessions require Pro/Pro+. Otherwise use one working tournament at a time.

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 22.1 — FAQ Section on Public Website              ║
║  File: docs/screenshots/fig_22_1_website_faq.png             ║
║  Capture: Public FAQ accordion                               ║
╚══════════════════════════════════════════════════════════════╝
```

---

# Chapter 23 – Troubleshooting

| Symptom | Likely cause | What to try |
|---------|--------------|-------------|
| Showcase blocked | No auction rules | Set Auction Rules and Apply |
| Wrong tournament on screen | Navbar working tournament | Switch tournament; reload |
| Projector stuck on pools | Board mode not idle | Open showcase / clear board mode |
| Bid rejected | Purse / tier / max players | Check remaining points & tier limits |
| Owner sees blank console | No team on user | Assign tournament + team |
| Images slow / huge PDFs | Large photos | Use compressed uploads; logo_card path for prints |
| Payment Tracker empty | No active tournament / rights | Assign Active Tournament + Payment Tracker group |
| Signup email missing | Mail server / spam | Check spam; resend from support |
| Account frozen page | Plan expired | Renew / upgrade via SaaS payment |

```
╔══════════════════════════════════════════════════════════════╗
║  📷 FIGURE 23.1 — Frozen / Expired Account Page              ║
║  File: docs/screenshots/fig_23_1_account_frozen.png          ║
║  Capture: Blocking page shown to frozen accounts             ║
╚══════════════════════════════════════════════════════════════╝
```

---

# Chapter 24 – Best Practices

1. **Dry-run** the full flow one day before the event (registration → showcase → sell → projector).
2. Finalise **slabs and purse** before owners arrive.
3. Pre-load **player photos**; reject blurry selfies at registration desk.
4. Use **Auctioneer Console + Projector** on separate machines.
5. Keep **Payment Tracker** staffed during registration.
6. Share **Live Board** link + tournament code only with intended audience.
7. Enable **Break Time** instead of leaving a stale player on screen during pauses.
8. Export **Sold / Unsold** immediately after the auction for settlement.
9. Do not unmask contacts unless your privacy process requires it.
10. Upgrade plan early if you need Owner bidding or mystery players—don’t wait until auction morning.

---

# Chapter 25 – Glossary

| Term | Definition |
|------|------------|
| Tournament | Top-level event container |
| Team / Franchise | Bidding entity with a purse |
| Purse / Points | Virtual budget used for bids |
| Tier | Player category used for limits and base prices |
| Draft | Player not yet in auction pool |
| In Auction | Player available to be called |
| Sold / Unsold | Final outcomes for a called player |
| Icon / Key Player | Special designated player for a team |
| Bid Slab | Increment rule for a price range |
| Player Showcase | Operator stage UI |
| Auctioneer Console | Dedicated bidding console |
| Owner Console | Mobile owner bidding UI |
| Projector | Audience-facing display |
| Live Board | Public web board of live bids |
| Working Tournament | Active tournament in navbar switcher |
| Mystery Player | Identity hidden until reveal |
| SaaS Plan | Subscription tier with limits/features |
| Registration Fee | Online fee collected via Razorpay |

---

# Chapter 26 – Support

| Channel | Details |
|---------|---------|
| Website | https://www.auctionchamp.live |
| Email | auctionchamp.live@gmail.com |
| In-app | Upgrade / plan screens may show **Contact Support for Higher** on Pro+ |

When contacting support, include:

- Tournament Code (`AC#…`)
- Login email
- Approximate time of issue
- Screenshots of the error
- Razorpay payment ID (if payment-related)

---

## Appendix A – Screenshot Capture Checklist

Use this list when gathering images for the final PDF/book layout. Tick when captured.

| Fig | Title | File | Done |
|-----|-------|------|------|
| 5.1 | Login Screen | `fig_5_1_login.png` | ☐ |
| 5.2 | Home / Apps Menu | `fig_5_2_home_apps.png` | ☐ |
| 5.3 | Auction Settings Menu | `fig_5_3_auction_settings_menu.png` | ☐ |
| 5.4 | Tournament Switcher | `fig_5_4_tournament_systray.png` | ☐ |
| 6.1 | User Access Rights | `fig_6_1_user_groups.png` | ☐ |
| 7.1 | Pricing Cards | `fig_7_1_pricing_plans.png` | ☐ |
| 7.2 | SaaS Account | `fig_7_2_saas_account.png` | ☐ |
| 7.3 | Upgrade Request | `fig_7_3_upgrade_request.png` | ☐ |
| 7.4 | Upgrade Checkout | `fig_7_4_upgrade_checkout.png` | ☐ |
| 8.1 | Homepage Hero | `fig_8_1_homepage_hero.png` | ☐ |
| 8.2 | Get Started | `fig_8_2_get_started.png` | ☐ |
| 8.3 | Signup Form | `fig_8_3_signup_form.png` | ☐ |
| 8.4 | Signup Done | `fig_8_4_signup_done.png` | ☐ |
| 8.5 | Website Configurator | `fig_8_5_website_config.png` | ☐ |
| 9.1 | Create Tournament | `fig_9_1_tournament_create.png` | ☐ |
| 9.2 | Tournament Actions | `fig_9_2_tournament_actions.png` | ☐ |
| 9.3 | Presentation & Theme | `fig_9_3_presentation_theme.png` | ☐ |
| 9.4 | Registration Payment | `fig_9_4_registration_payment.png` | ☐ |
| 10.1 | Team Form | `fig_10_1_team_form.png` | ☐ |
| 10.2 | Upload Teams | `fig_10_2_upload_teams.png` | ☐ |
| 10.3 | Auction Team(s) | `fig_10_3_auction_teams.png` | ☐ |
| 11.1 | Players Menus | `fig_11_1_players_menus.png` | ☐ |
| 11.2 | Registration Form | `fig_11_2_registration_form.png` | ☐ |
| 11.3 | Registration Success | `fig_11_3_registration_success.png` | ☐ |
| 11.4 | Reg Razorpay | `fig_11_4_reg_razorpay.png` | ☐ |
| 11.5 | Player Form | `fig_11_5_player_form.png` | ☐ |
| 11.6 | Upload Players | `fig_11_6_upload_players.png` | ☐ |
| 11.7 | Player Actions | `fig_11_7_player_actions.png` | ☐ |
| 11.8 | Icon Player Wizard | `fig_11_8_icon_player_wizard.png` | ☐ |
| 12.1 | Auction Rules | `fig_12_1_auction_rules.png` | ☐ |
| 13.1 | Rules Required | `fig_13_1_rules_required.png` | ☐ |
| 13.2 | Showcase | `fig_13_2_showcase.png` | ☐ |
| 13.3 | Dice Call-Up | `fig_13_3_dice_callup.png` | ☐ |
| 13.4 | Sell Modal | `fig_13_4_sell_modal.png` | ☐ |
| 13.5 | Sold Stamp | `fig_13_5_sold_stamp.png` | ☐ |
| 13.6 | Break Time | `fig_13_6_break_time.png` | ☐ |
| 14.1 | Auctioneer Console | `fig_14_1_auctioneer_console.png` | ☐ |
| 14.2 | Place Bid Modal | `fig_14_2_place_bid_modal.png` | ☐ |
| 14.3 | Mystery Reveal | `fig_14_3_mystery_reveal.png` | ☐ |
| 15.1 | Owner Console Mobile | `fig_15_1_owner_console_mobile.png` | ☐ |
| 15.2 | Owner Console Desktop | `fig_15_2_owner_console_desktop.png` | ☐ |
| 16.1 | Projector Player | `fig_16_1_projector_player.png` | ☐ |
| 16.2 | Projector Sponsor | `fig_16_2_projector_sponsor.png` | ☐ |
| 16.3 | Live Board Unlock | `fig_16_3_live_board_unlock.png` | ☐ |
| 16.4 | Live Bid Board | `fig_16_4_live_board.png` | ☐ |
| 16.5 | Team Balance | `fig_16_5_team_balance.png` | ☐ |
| 17.1 | Payment Tracker | `fig_17_1_payment_tracker.png` | ☐ |
| 17.2 | Razorpay Settings | `fig_17_2_razorpay_settings.png` | ☐ |
| 18.1 | Player Card | `fig_18_1_player_card.png` | ☐ |
| 18.2 | PDF to PNG | `fig_18_2_pdf_to_png.png` | ☐ |
| 18.3 | Export Sold/Unsold | `fig_18_3_export_sold_unsold.png` | ☐ |
| 19.1 | WhatsApp Settings | `fig_19_1_whatsapp_settings.png` | ☐ |
| 19.2 | Share WhatsApp | `fig_19_2_share_whatsapp.png` | ☐ |
| 19.3 | Player Notify Buttons | `fig_19_3_player_notify_buttons.png` | ☐ |
| 20.1 | Player Tier | `fig_20_1_player_tier.png` | ☐ |
| 20.2 | Contact Privacy | `fig_20_2_contact_privacy.png` | ☐ |
| 21.1 | Pool Generator | `fig_21_1_pool_generator.png` | ☐ |
| 21.2 | Projector Pools | `fig_21_2_projector_pools.png` | ☐ |
| 22.1 | Website FAQ | `fig_22_1_website_faq.png` | ☐ |
| 23.1 | Account Frozen | `fig_23_1_account_frozen.png` | ☐ |

## Appendix B – Cover Page Placeholder (Book Layout)

```
╔══════════════════════════════════════════════════════════════╗
║  📷 COVER — AuctionChamp User Manual                         ║
║  File: docs/screenshots/cover_auctionchamp_user_manual.png   ║
║  Capture / design: Branded cover with logo, title, version,  ║
║  website URL, and year                                       ║
╚══════════════════════════════════════════════════════════════╝
```

**Suggested cover text**

- Title: **AuctionChamp User Manual**
- Subtitle: Sports Player Auction Management Platform
- Version 1.0 — July 2026
- www.auctionchamp.live

---

*End of AuctionChamp User Manual v1.0*
