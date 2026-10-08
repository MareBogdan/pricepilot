# Deployment

Two parts. **Part A is the live deploy** (Hugging Face Spaces, free). **Part B is a reference
walk-through for a Hetzner VPS: it is NOT deployed and nothing in it has been executed.** Read
ADR-0051 for why.

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

## Part A -- Hugging Face Spaces (live deploy)

### What a Space is

A Space is a git repository on huggingface.co. When you push to it, Hugging Face builds the
`Dockerfile` in it and runs the container. With `sdk: docker` in the README header (already there),
HF routes the public URL to the port named in `app_port` (7860, which our `CMD` listens on). Free
tier: CPU basic, public URL, **it goes to sleep after a period of inactivity (about 48 h on the free
tier) and wakes on the next visit**; the wake-up takes roughly a minute while the container starts.

### How the 397 MB model stays out (the mechanism, tested)

Two layers, both in the repo:

1. `models/` and `data/` are in `.gitignore`, so the model was never committed. Nothing in the
   normal git history contains it.
2. You do **not** push the whole repo anyway. `scripts/make_space_bundle.ps1` copies only what the
   image needs (Dockerfile, `.dockerignore`, `README.md`, `pyproject.toml`, `src/`, `services/`,
   `config/`, three result JSONs) into a fresh folder with a fresh one-commit git repo, and **fails
   if any file is over 5 MB** or is a `.zip` / `.onnx` / weights file. Result: 73 files, 0.47 MB, no
   project history, no `docs/archive`, no labels. The Space is built from that folder (tested: the
   bundle builds and serves against Neon with no "n/a").

### Steps (you do these; none of them is done yet)

1. **Account.** Create a free account on huggingface.co (or log in).
2. **Write token.** Settings -> Access Tokens -> New token, type **Write**, name it `pricepilot-deploy`.
   Copy it once; it is your git password for step 7. Never commit it.
3. **Read-only database role (strongly recommended).** The Space is public and the app only reads.
   Do not give it your Neon owner password. In the Neon SQL editor run (pick your own password):
   ```sql
   CREATE ROLE pricepilot_readonly LOGIN PASSWORD '<generate-a-long-one>';
   GRANT USAGE ON SCHEMA public TO pricepilot_readonly;
   GRANT SELECT ON ALL TABLES IN SCHEMA public TO pricepilot_readonly;
   ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO pricepilot_readonly;  -- tables added by later migrations
   ```
   Your `DATABASE_URL` for the Space is the same URL as in `.env` with that role and password
   (keep `?sslmode=require`; the psycopg driver on Linux accepts the Neon parameters as they are).
   If you skip this step you can use the existing URL, but then a bug or a leaked secret can write.
4. **Create the Space.** huggingface.co -> New -> Space. Name `pricepilot`, SDK **Docker** (blank
   template), hardware **CPU basic (free)**, visibility **Public**. Do not add files in the web form.
5. **Set the secret.** Space -> Settings -> *Variables and secrets* -> **New secret**: name
   `DATABASE_URL`, value = the URL from step 3. (Secret, not Variable: variables are public.)
   Secrets are passed to the running container as environment variables, which is where
   `pricepilot.config` reads `DATABASE_URL` from.
6. **Build the bundle.** From the repo root in PowerShell:
   ```powershell
   .\scripts\make_space_bundle.ps1
   ```
   It prints `Bundle ready: ...\pricepilot-space (0.47 MB, 73 files)`.
7. **Push it.** (Replace `<user>`.) When git asks for a password, paste the write token.
   ```powershell
   cd $env:TEMP\pricepilot-space
   git remote add space https://huggingface.co/spaces/<user>/pricepilot
   git push space main --force
   ```
   `--force` is correct here: the bundle is a fresh one-commit repo and the Space starts with a
   placeholder commit. It overwrites only the Space, not GitHub.
8. **Watch the build.** Space page -> *Logs* (build, then container). First build takes a few minutes.
   Status turns **Running**.
9. **Public URL.** The Space page itself is `https://huggingface.co/spaces/<user>/pricepilot`; the
   app alone, which is what you link and embed, is `https://<user>-pricepilot.hf.space`. Open it,
   check the home page, a product page and `/status`, then paste the URL into the README placeholder
   ("Live demo") and tell Claude so the demo GIF can be recorded from it.

### Redeploy

Change code in the main repo, commit as usual, then repeat steps 6-7 (`make_space_bundle.ps1`, then
`git push space main --force` from the bundle folder). The Space rebuilds on every push. Changing
the secret (Settings) restarts the container without a rebuild.

### Cold start and sleeping

- Sleeping Space: first visit shows HF's "starting" page for about a minute. Say so in the README
  (it does).
- Neon also scales to zero when idle; the first query after that retries (`connect_with_wakeup_retry`
  in `db.py`), so the first page after a long gap can take several extra seconds.
- Free Spaces have no persistent disk and need none: the app is stateless.

### Troubleshooting

| Symptom | Likely cause |
|---|---|
| Build fails at `uv pip install` | `pyproject.toml` in the bundle is stale; rebuild the bundle |
| Page shows 503 / `/health` says `degraded` | `DATABASE_URL` secret missing, wrong, or the role lacks SELECT |
| Tiles say "n/a" | a result JSON missing from the bundle; `tests/test_serving_image.py` guards the list |
| `git push` asks for a password again | wrong token type (needs **Write**) or wrong username |

---

## Part B -- Hetzner VPS (reference / future, NOT currently deployed)

> Nothing below has been run. It is the ops walk-through CLAUDE.md asked for, kept so the VPS option
> is a one-evening job if the Space is ever outgrown (always-on, custom domain, running the matcher
> as a daily batch next to the app). Cost: CX23-class, about $23 for three months (ESTIMATE,
> ADR-0030, `docs/phase3-serving-prices.md`); check the live price before buying. Only the free
> Space is live, so `docs/COSTS.md` records $0 for hosting.

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
nano .env        # DATABASE_URL=<the read-only Neon URL, see Part A step 3>; nothing else is needed to serve
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

Record the actual price in `docs/COSTS.md` in the same commit, update ADR-0051/ADR-0030, and run the
matcher as the incremental batch described in CLAUDE.md section 6 (that is the point at which the
ML dependencies come back, in a separate image, not in this serving one).
