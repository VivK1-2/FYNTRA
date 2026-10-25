# Deploying the FYNTRA backend on a VPS

Tested layout: Ubuntu 22.04/24.04, 2 vCPU, 4 GB RAM, 40 GB disk (PDF parsing later needs the RAM).

## 0. Before you start
- Point a DNS **A record** `api.yourdomain.com` at the VPS IP (Caddy needs this to issue HTTPS).
- Have an SSH key ready. Do not use password login.

## 1. Harden the server (one time)
```bash
adduser deploy && usermod -aG sudo deploy
# copy your SSH public key to /home/deploy/.ssh/authorized_keys, then:
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sudo systemctl restart ssh

sudo ufw default deny incoming && sudo ufw default allow outgoing
sudo ufw allow OpenSSH && sudo ufw allow 80/tcp && sudo ufw allow 443/tcp
sudo ufw enable
sudo apt-get update && sudo apt-get install -y fail2ban unattended-upgrades
```
Postgres is **not** published on any port; only Caddy listens publicly.

## 2. Install Docker
```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker deploy   # log out and back in
```

## 3. Get the code and configure
```bash
git clone <your-repo-url> fyntra-backend && cd fyntra-backend
cp deploy/.env.production.example .env && chmod 600 .env
openssl rand -hex 32   # use for API_KEY; run again for POSTGRES_PASSWORD
nano .env              # set API_DOMAIN, API_KEY, POSTGRES_PASSWORD, CORS_ORIGINS,
                       # SEC_USER_AGENT (real email), LLM_API_KEY, LLM_MODEL
```

## 4. Start
```bash
docker compose -f docker-compose.prod.yml --env-file .env up -d --build
docker compose -f docker-compose.prod.yml logs -f api     # wait for "Application startup complete"
```
Migrations run automatically on every start.

## 5. Verify (from your laptop)
```bash
curl https://api.yourdomain.com/health
docker compose -f docker-compose.prod.yml exec api python scripts/check_llm.py   # confirms the model answers
```
If the check fails, fix `LLM_MODEL`, `LLM_BASE_URL` or `LLM_API_KEY` in `.env`, then run `docker compose -f docker-compose.prod.yml restart api`.


## 6. Operations
| Task | Command |
|---|---|
| Update | `git pull && docker compose -f docker-compose.prod.yml up -d --build` |
| Logs | `docker compose -f docker-compose.prod.yml logs -f api` |
| DB backup | `docker compose -f docker-compose.prod.yml exec db pg_dump -U fyntra fyntra \| gzip > backup_$(date +%F).sql.gz` |
| Restart on reboot | automatic (`restart: unless-stopped`) |

Add a daily cron for the backup and copy it off the VPS.

## Known VPS risks
- Google/Yahoo/NSE/BSE may block datacenter IPs. Test each from the VPS early; an India-region VPS helps NSE/BSE.
- The frontend must call the API **from its server side** or hold the API key in a backend-for-frontend; a key in browser JavaScript is public.
