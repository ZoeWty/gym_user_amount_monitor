# Cloud deployment

Runs the collector continuously so the history has no holes. A laptop sleeps;
that is the whole reason for this document. Every morning the laptop misses is
a morning that can never be backfilled.

The web dashboard is secondary here. If the API is down for an hour you refresh
later. If the collector is down for an hour, that hour is gone permanently.

## What you are deploying

The same `docker-compose.yml` that runs locally, on one VM:

```
        every 10 min
poller ──────────────► booking-tpsc.sporetrofit.com  (12 venues, 1 POST)
   │                   wssc.cyc.org.tw               (文山 ice rink only)
   │ INSERT
   ▼
postgres ◄──── api ◄──── cloudflared ◄──── you, on your phone
(volume)                  (outbound only)
```

**Postgres shares the VM with the collector.** That was decided deliberately:
fewer moving parts, one thing to operate. The cost is that this VM is the only
copy of the data, which is why the backup step below is not optional.

## Sizing

Measured on the running stack, not estimated:

| | RAM |
|---|---|
| postgres | 21 MB |
| api | 42 MB |
| poller | 29 MB |
| **total** | **~92 MB** |

Disk: one 308 MB image, plus roughly 150–200 MB of database growth per year
(1.3M rows at 25 areas polled every 10 minutes, including indexes).

**A 1 GB / 1 vCPU / 10 GB instance is enough.** Take 2 GB if you want headroom
to build the image without swapping — `npm ci` is the heaviest moment.

One caveat if you later move Dify onto the same box: its stack is a different
order of magnitude (~2.5 GB across its containers, measured locally). Size for
that separately; do not assume this 1 GB box absorbs it.

## Steps

### 1. Create the VM

Any provider. Ubuntu 24.04 LTS, 1 GB RAM minimum. You need SSH access and
nothing else — no inbound HTTP ports, see step 6.

### 2. Install Docker

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
```

Log out and back in so the group membership applies, then confirm:

```bash
docker compose version
```

### 3. Clone and configure

```bash
git clone https://github.com/ZoeWty/gym_user_amount_monitor.git
cd gym_user_amount_monitor
python3 -c "import secrets; print('POSTGRES_PASSWORD=' + secrets.token_urlsafe(24))" > .env
```

`.env` is gitignored. Do not reuse your local password — a separate secret per
environment means a leak from one does not reach the other.

### 4. Start

```bash
docker compose up -d --build
```

Build on the VM rather than pushing an image from your Mac. Your laptop is
arm64 and the VM is almost certainly amd64; building here sidesteps the whole
cross-architecture problem.

First build takes a few minutes (`npm ci` plus `pip install`). Afterwards:

```bash
./check.sh ngsc
```

All six steps should pass and step 3 should show 12 venues.

### 5. Daily backup

`scripts/backup.sh` dumps the database **and restores the dump into a throwaway
database to verify it**, exiting non-zero if the row counts disagree. The drill
is inside the backup rather than a separate script you have to remember.

```bash
crontab -e
```

```cron
0 4 * * * cd $HOME/gym_user_amount_monitor && ./scripts/backup.sh >> backup.log 2>&1
```

Cron uses the VM's local time, which is UTC on a default Ubuntu image. 04:00
UTC is 12:00 in Taipei — pick an hour that is not a busy collection period if
you care, though the dump is fast enough that it does not really matter.

**Write the dumps somewhere other than this VM.** A backup on the machine it is
protecting only survives the failures that do not destroy the machine. Pass a
mounted path as the argument:

```cron
0 4 * * * cd $HOME/gym_user_amount_monitor && ./scripts/backup.sh /mnt/backups >> backup.log 2>&1
```

Check it ran at least once before trusting it:

```bash
tail -3 backup.log     # expect: "verified: N rows restored, newest ..."
```

### 6. Public access

`docker-compose.yml` binds both Postgres and the API to `127.0.0.1`, so nothing
is reachable from the internet yet. Keep it that way: expose the dashboard
through a Cloudflare Tunnel, which dials **outbound**, so the VM needs no
inbound port open at all.

1. In Cloudflare Zero Trust, create a tunnel with a public hostname pointing at
   `http://api:8000`.
2. Add the token to `.env` as `CLOUDFLARE_TUNNEL_TOKEN=...`
3. Add an Access policy allowing only your own email.
4. Start it:

```bash
docker compose --profile public up -d
```

The application contains no authentication code. Access handles it, which also
means swapping to a different front door later changes nothing in the app.

## Verify before you walk away

```bash
# all four services up, db healthy
docker compose ps

# collector actually collecting, 12 venues
./check.sh ngsc

# nothing exposed to the internet — expect closed/filtered on both
nmap -Pn -p 5432,8000 <vm-public-ip>

# the dashboard requires login, from your phone on mobile data
```

That `nmap` line is the one people skip. A misconfigured port binding produces
no error message and no symptom — you only find out when someone else does.

## Recovering from a lost VM

```bash
# on a fresh VM, after steps 1-4
gunzip -c gym-YYYYMMDD-HHMMSS.sql.gz | docker compose exec -T db psql -U gym -d gym
./check.sh ngsc
```

This is the path the nightly verification exercises, so it is not the first
time the dump has been read back.

## Updating

```bash
git pull && docker compose up -d --build
```

**`--build` is not optional.** Without it Compose reuses the existing image, so
your changes do not take effect while the container still reports `Up` and the
logs still show successful polls. Nothing tells you. Confirm what is actually
running:

```bash
docker compose exec -T poller grep -c "def parse_aggregate" poll.py   # expect 1
```

## Deliberately not included

- **Kubernetes.** One VM running three containers does not need an orchestrator.
  Manifests exist in `k8s/` for when you want to learn it; they are not a
  prerequisite for running this.
- **CI/CD.** `git pull && docker compose up -d --build` is the deploy. Automate
  it when deploying by hand becomes annoying, not before.
- **Managed Postgres.** Rejected during design: a separate managed database
  would survive losing this VM, at the cost of another service to run. The
  backup covers the same failure. Revisit if restoring by hand ever feels slow
  enough to matter.
- **Monitoring and alerting.** The dashboard turns its timestamp red after 15
  minutes without data, which is the signal that matters. Add real alerting when
  you start relying on this and cannot check it yourself.
- **Multiple replicas.** The poller must not run twice concurrently — two
  instances would double-write at different timestamps, which the
  `(venue, area, ts)` key does not deduplicate.
