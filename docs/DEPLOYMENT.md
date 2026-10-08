# Deployment

Two parts. **Part A is the live deploy** (Render, free tier). **Part B is a reference walk-through
for a Hetzner VPS: it is NOT deployed and nothing in it has been executed.** Read ADR-0051 and
ADR-0052 for why. Short version: **Hugging Face Docker Spaces became paid in 2026-10, so the live
host is Render's free tier**; the dashboard is FastAPI + Jinja, not Gradio, so it was retargeted
rather than rewritten.

What gets deployed in both cases is the same thing: the **lean serving image** built from the root
`Dockerfile`. It runs the read-only dashboard + JSON API (`pricepilot.api.main:app`) and nothing
else. It contains no `torch` / `transformers` / `onnxruntime` / `sentence-transformers` and no model
file, because the dashboard only reads Neon, `config/pricing-policy.toml` and three committed result
JSONs. Matching, embeddings and RAG run in the pipeline (your machine / Kaggle / CI), never in this
container. `tests/test_serving_image.py` fails if that stops being true.

Verified locally before this was written: the image is 324 MB, serves `/health`, `/`, `/status`,
`/products/1`, `/api/status` and `/static/*` with HTTP 200 against Neon, no tile reads "n/a", and
with an unreachable database `/health` answers `degraded` and pages answer 503 (no stack trace).

---

## Part A -- Render, free tier (live deploy)

### What Render does

Render connects to the GitHub repo, reads `render.yaml` (a "Blueprint": one free web service built
from the root `Dockerfile`), builds the image on its servers and runs it. It injects a `PORT`
environment variable (10000 by default) and routes the public HTTPS URL to that port; the
`Dockerfile` `CMD` listens on `${PORT:-7860}`, so the same image runs locally and on Render.
`/health` is the health check. The build uses the git clone, and `models/` and `data/` are
git-ignored (never committed), so the 397 MB model cannot reach the build; the `Dockerfile` also
copies only `src/`, `services/`, `config/` and three result JSONs.

Verified locally: with `PORT=10000` the container answered `/health`, `/`, `/status` and
`/products/1` with HTTP 200 against Neon, no "n/a" tiles; without `PORT` it listens on 7860.

### Steps (you do these; none of them is done yet)

1. **Read-only database role.** (Already created: `pricepilot_readonly`.) The Render service is
   public and the app only reads, so it must never get the Neon owner URL. If you need to redo it,
   in the Neon SQL editor:
   ```sql
   CREATE ROLE pricepilot_readonly LOGIN PASSWORD '<generate-a-long-one>';
   GRANT USAGE ON SCHEMA public TO pricepilot_readonly;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO pricepilot_readonly;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO pricepilot_readonly;
   ```
   The `DATABASE_URL` for Render is the `.env` URL with that role and password
   (`postgresql+psycopg://pricepilot_readonly:<password>@<host>/<db>?sslmode=require`; the psycopg
   driver on Linux takes the Neon parameters as they are, no pg8000 here).
2. **Account.** render.com -> Get Started -> sign in with GitHub (simplest, it also links the repo).
   As far as I know the free web service does not need a card; if Render asks for one and you do not
   want to give it, use **Koyeb** (free Docker web service) as the backup: same Dockerfile, set the
   `PORT` and `DATABASE_URL` variables there. Check the card question on the sign-up screen.
3. **Create the service.** Dashboard -> **New +** -> **Blueprint** -> pick the
   `MareBogdan/pricepilot` repo (if it is private, grant Render access to it when GitHub asks;
   "Only select repositories" -> `pricepilot` is enough). Render finds `render.yaml` and shows one
   service, `pricepilot`, plan **Free**.
   If Blueprints are not available on your plan: **New +** -> **Web Service** -> same repo ->
   Language/Runtime **Docker** -> Branch `main` -> Instance type **Free** -> Health Check Path `/health`.
4. **Set the secret.** When the Blueprint form asks for `DATABASE_URL` (it is declared with
   `sync: false`, so the value is never in git), paste the read-only URL from step 1. For the manual
   route: Environment -> Add Environment Variable -> `DATABASE_URL`. Do not paste the owner URL.
5. **Deploy.** Click **Apply** / **Create Web Service**. Watch *Logs*: build (a few minutes), then
   `Uvicorn running on http://0.0.0.0:10000`, then the service shows **Live**.
6. **Public URL.** `https://<name>.onrender.com` (shown at the top of the service page; the name is
   `pricepilot` unless taken). Open it and check the home page, a product page and `/status`, then
   send the URL so it goes into the README ("Live demo") and the demo GIF can be recorded from it.

### Redeploy

`render.yaml` sets `autoDeploy: false` on purpose (CLAUDE.md rule 6: deployment is always a manual
step), so pushing to `main` does NOT change the live site. To deploy a new commit: service page ->
**Manual Deploy** -> *Deploy latest commit*. To
change the secret: Environment -> edit `DATABASE_URL` -> Save (the service restarts).

### Cold start and sleeping

- A free Render web service **spins down after about 15 minutes without traffic** and starts again
  on the next request; that first request takes roughly a minute while the container boots. The
  README says so. Free instances also have no persistent disk, which is fine: the app is stateless.
- Neon also scales to zero when idle; the first query after that retries (`connect_with_wakeup_retry`
  in `db.py`), so the first page after a long gap can take several extra seconds on top.
- Render's free instance hours are limited per month; one idle-sleeping demo stays well inside them
  (verify the current numbers on the pricing page; they change).

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Build fails at `uv pip install` or the import check | `pyproject.toml` core dependencies and the code disagree; the import check in the `Dockerfile` is meant to fail here |
| Deploy "timed out waiting for port" | the app is not listening on `$PORT`; the `CMD` must be the shell form in the `Dockerfile` |
| Page shows 503 / `/health` says `degraded` | `DATABASE_URL` missing, wrong, or the role lacks SELECT |
| Tiles say "n/a" | a result JSON is missing from the image; `tests/test_serving_image.py` guards the list |

### Legacy: Hugging Face Space

`scripts/make_space_bundle.ps1` and the README front-matter (`sdk: docker`, `app_port: 7860`) are
kept but unused: they built a Docker Space, which HF made paid. They are harmless on GitHub and Render.

---

## Part B -- Hetzner VPS (reference / future, NOT currently deployed)

> Nothing below has been run. It is the ops walk-through CLAUDE.md asked for, kept so the VPS option
> is a one-evening job if the Render free tier is ever outgrown (always-on, custom domain, running the matcher
> as a daily batch next to the app). Cost: CX23-class, about $23 for three months (ESTIMATE,
> ADR-0030, `docs/phase3-serving-prices.md`); check the live price before buying. Only the
> Render free tier is live, so `docs/COSTS.md` records $0 for hosting.

The shape: one small Linux server; **Caddy** (reverse proxy that fetches and renews HTTPS
certificates by itself) in front of the **API container**; the database stays on **Neon**
(managed, so there is no database container to back up or patch).

### 1. Server and SSH key

An SSH key pair replaces passwords: the private half never leaves your laptop, the public half sits
on the server.
```powershell
ssh-keygen -t ed25519 -C "pricepilot-vps"      # accept the default path, set a passphrase
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub   # this is the PUBLIC key; paste it into Hetzner
```
In the Hetzner Cloud console: new project -> add server, Ubuntu 24.04 LTS, the CX23-class type,
nearest EU location, paste the public key under *SSH keys*. Note the server's IPv4.
First login: `ssh root@<ip>`.

### 2. Non-root user and SSH hardening

Root with a password is what every bot on the internet tries. Make a normal user, then turn root and
password logins off.
```bash
adduser deploy && usermod -aG sudo deploy
mkdir -p /home/deploy/.ssh && cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh && chmod 700 /home/deploy/.ssh && chmod 600 /home/deploy/.ssh/authorized_keys
```
**In a second terminal, confirm `ssh deploy@<ip>` works before continuing** (otherwise the next step
can lock you out). Then:
```bash
sudo tee /etc/ssh/sshd_config.d/10-hardening.conf <<'EOF'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
EOF
sudo systemctl reload ssh
```

### 3. Firewall and automatic patches

Only SSH (22), HTTP (80) and HTTPS (443) should be reachable. Port 80 is needed for Caddy's
certificate challenge and the redirect to HTTPS.
```bash
sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw enable
sudo apt update && sudo apt install -y fail2ban unattended-upgrades   # bans repeated bad SSH logins; installs security patches
```
Also enable the Hetzner Cloud Firewall (same three ports) as a second layer outside the server.
**Docker trap:** a container port published with `ports:` bypasses `ufw`. That is why the compose
file below publishes only Caddy's 80/443 and gives the API `expose:` (internal network only).

### 4. Docker

Install from Docker's official apt repository (docs.docker.com/engine/install/ubuntu), then
`sudo usermod -aG docker deploy` and log in again. Check with `docker compose version`.

### 5. Domain and DNS

Buy a domain anywhere. DNS is the phone book: add an **A record** `pricepilot.<yourdomain>` ->
the server IPv4 (and an AAAA record -> the IPv6 if you want it). Wait until
`nslookup pricepilot.<yourdomain>` returns the IP; Caddy cannot get a certificate before that.

### 6. App, compose and Caddy

```bash
git clone https://github.com/<github-user>/pricepilot.git && cd pricepilot
nano .env        # DATABASE_URL=<the read-only Neon URL, see Part A step 1>; nothing else is needed to serve
```
`docker-compose.prod.yml` (to be created when this is executed; it is not in the repo today):
```yaml
services:
  api:
    build: .
    restart: unless-stopped
    env_file: .env
    expose: ["7860"]            # internal only; Caddy is the sole way in
  caddy:
    image: caddy:2
    restart: unless-stopped
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data        # the certificates; losing it means re-issuing, nothing worse
      - caddy_config:/config
    depends_on: [api]
volumes:
  caddy_data:
  caddy_config:
```
`Caddyfile` (two lines of real configuration; HTTPS, renewal and the HTTP->HTTPS redirect are automatic):
```
pricepilot.<yourdomain> {
    reverse_proxy api:7860
}
```
Start: `docker compose -f docker-compose.prod.yml up -d --build`. Check
`docker compose -f docker-compose.prod.yml logs caddy` for "certificate obtained", then open the
domain. `restart: unless-stopped` brings both back after a reboot (Docker itself starts at boot).

### 7. Volumes, updates, monitoring

- **Volumes:** only `caddy_data` / `caddy_config`. The API is stateless; the database is Neon.
- **Update:** `git pull && docker compose -f docker-compose.prod.yml up -d --build`.
- **Look:** `docker compose ... ps`, `docker stats`, `/health` returns `status`/`database`.
  A free uptime ping (UptimeRobot or similar) on `/health` is enough for a portfolio.

### 8. Backups (the part people skip)

- The data that matters is in Neon. Check your Neon plan's point-in-time-restore window (it differs
  by plan and is short on the free one) and treat it as short-term safety only.
- Own copy, weekly, from the server (install `postgresql-client` first; the dump goes over TLS to Neon):
  ```bash
  pg_dump "$DATABASE_URL_PLAIN" -Fc -f ~/backups/pricepilot-$(date +%F).dump
  ```
  (`DATABASE_URL_PLAIN` is the URL without the `+psycopg` part, which `pg_dump` does not understand.)
  Run it from cron (`crontab -e`: `0 3 * * 0 ...`), keep the last 4, and copy the newest off the
  server (Hetzner Storage Box, or `scp` to your laptop). A backup on the same disk as the thing it
  backs up is not a backup.
- **Test a restore** once into a scratch Neon branch (`pg_restore -d <scratch-url> file.dump`).
  Until you have, you only have files, not backups.
- Hetzner's server snapshot option (a paid add-on) covers the server config, not the data.

### 9. If the VPS is ever executed

Record the actual price in `docs/COSTS.md` in the same commit, update ADR-0052/ADR-0030, and run the
matcher as the incremental batch described in CLAUDE.md section 6 (that is the point at which the
ML dependencies come back, in a separate image, not in this serving one).
