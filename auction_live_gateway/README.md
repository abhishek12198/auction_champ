# AuctionChamp — Phase 2B Redis Live Gateway

Lightweight FastAPI service that serves Live Board / Projector / Bid Summary
poll JSON **directly from Redis**. Odoo is not imported. PostgreSQL is not used.

```
Browser → Nginx → Gateway (127.0.0.1:8090) → Redis
                   ↘ 404/503 → Nginx → Odoo (fallback)
```

## Install

```bash
cd /home/abhishek/PycharmProjects/auction_champ/auction_live_gateway
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## Run (foreground)

```bash
export AUCTION_REDIS_URL=redis://127.0.0.1:6379/1
./venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090 --log-level warning
```

## Health

```bash
curl -sS http://127.0.0.1:8090/health
curl -sS http://127.0.0.1:8090/ready
```

## Prerequisites (Odoo / Redis)

1. Phase 2A snapshots enabled: `auction.redis.enabled = True`
2. Fix applied: seq `0` is a valid HIT
3. Slug map populated:

```bash
# Odoo shell
env['auction.tournament'].action_backfill_redis_slug_map()
env.cr.commit()
```

4. Snapshots exist (trigger one poll via Odoo or a watched mutation so meta
   includes `live_board_active` / `code_protected`).

## Live Board protection (Option A)

Gateway reads Redis meta:

- `live_board_active=0` → returns `{"live_board_active": false}` (200)
- `code_protected=1` → **404** so Nginx falls back to Odoo (cookie/unlock)
- Unprotected + active → Redis HIT

## Tests

```bash
cd auction_live_gateway
./venv/bin/python -m unittest discover -s tests -v
```

## systemd (do not enable until reviewed)

```bash
sudo cp deploy/auction-redis-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now auction-redis-gateway
sudo systemctl status auction-redis-gateway
```

## Nginx (do not apply until gateway tests pass)

See `deploy/nginx-auction-live-gateway.snippet.conf`.

1. Add `upstream auction_live_gateway` (or include file)
2. Paste the three `location` blocks **before** `location /`
3. `sudo nginx -t && sudo systemctl reload nginx`

### Rollback

Comment out the three gateway `location` blocks, reload Nginx.
Optionally: `sudo systemctl stop auction-redis-gateway`.

Browser → Odoo `:8069` again. Also `auction.redis.enabled = False` still
uses the Phase 2A ORM path when hitting Odoo directly.

## Load test

Use the gateway venv (includes `httpx`):

```bash
GW_PY=./auction_live_gateway/venv/bin/python

# Gateway path
$GW_PY scripts/load_test_live_polls.py --run --viewers 100 --duration 10 \
  --base http://127.0.0.1:8090 --db main_db_1 --slug jas-cricket-league

# Odoo path (baseline)
$GW_PY scripts/load_test_live_polls.py --run --viewers 100 --duration 10 \
  --base http://127.0.0.1:8069 --db main_db_1 --slug jas-cricket-league
```

`--viewers N` = **N concurrent paced clients** (not `N//4` threads).

Do **not** publish a supported viewer count from localhost alone.

## Backfill (existing tournaments)

```bash
# Slug map + gateway meta flags from PostgreSQL via redis-cli
python3 scripts/backfill_redis_slug_map.py --db YOUR_DB
```

After deploying Odoo code that writes full meta, restart Odoo workers so
`live_board_active` / `code_protected` are included on every snapshot write.
