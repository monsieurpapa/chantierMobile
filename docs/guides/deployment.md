# Deployment

Three supported targets: **Render.com** (free tier, easiest), **Railway** (paid,
simplest config), and a **bare Linux server** (full control). All three build from the
same `Dockerfile` / `requirements.txt` and run `python manage.py migrate` +
`collectstatic` before starting Gunicorn.

## Render.com (free)

Render hosts the full stack for free using the included `render.yaml` blueprint. Free
tier limitations: the web service sleeps after 15 minutes of inactivity (~30s cold
start), and the PostgreSQL instance expires after 90 days (migrate to Supabase before
then).

### Prerequisites

- A free [Render account](https://render.com)
- A free [Upstash account](https://upstash.com) for Redis (10K commands/day, no expiry)

### 1. Create a free Redis database on Upstash

1. Log in to Upstash → **Create Database**
2. Choose the region closest to your users
3. Copy the **Redis URL** — it starts with `rediss://`

### 2. Deploy via Blueprint

1. In the Render dashboard click **New → Blueprint**
2. Connect your GitHub repo (`monsieurpapa/chantierMobile`)
3. Render reads `render.yaml` and proposes three resources:
   - `chantiermobile-web` — Django web service
   - `chantiermobile-celery` — Celery worker + beat scheduler
   - `chantiermobile-db` — managed PostgreSQL (free, 90 days)
4. Before clicking **Apply**, set the `REDIS_URL` environment variable on **both
   services** to the Upstash URL copied above
5. Click **Apply** — Render runs `build.sh` (install → collectstatic → migrate) and
   starts the services

### 3. Create a superuser

Once the deploy is green, open the **Shell** tab on `chantiermobile-web` and run:

```bash
python manage.py createsuperuser
```

### 4. Access the app

Your live URL will be: `https://chantiermobile-web.onrender.com`

Log in, create a Cabinet, and assign yourself a role to unlock the full interface (see
[`getting-started.md`](getting-started.md#creating-your-first-cabinet)).

### PostgreSQL expiry (90-day migration to Supabase)

Render's free PostgreSQL is deleted after 90 days. Before that deadline:

1. Dump from Render: in the Render shell run `pg_dump $DATABASE_URL > backup.sql`
2. Create a free project on [Supabase](https://supabase.com) — permanent free tier, 500 MB
3. Copy the Supabase connection string (PostgreSQL format, not Supabase JS)
4. Restore: `psql <supabase-connection-string> < backup.sql`
5. In the Render dashboard update `DATABASE_URL` on both services to the Supabase URL
6. Redeploy — zero downtime

Media files can similarly move to Cloudflare R2 (S3-compatible, 10GB free) — see the
`CLOUDFARE_R2_*` environment variables already scaffolded in `render.yaml`.

## Railway

Railway builds straight from `railway.toml` (Dockerfile builder) — simpler to configure
than Render, but no free tier.

1. Create a new Railway project from the GitHub repo
2. Add managed PostgreSQL and Redis plugins (or point `DATABASE_URL`/`REDIS_URL` at
   external ones)
3. Set `SECRET_KEY`, `DEBUG=0`, `ALLOWED_HOSTS` as service variables
4. Railway reads `railway.toml`'s `startCommand` — migrate + collectstatic + Gunicorn
   with gevent workers, tuned for Railway's networking model (`--worker-class gevent
   --workers 4 --worker-connections 200`)
5. Healthcheck is configured against `/` with a 300s timeout and automatic restart on
   failure (`restartPolicyType = "ON_FAILURE"`, up to 10 retries)

## Bare Linux Server

For full control on a VPS (Ubuntu 22.04 LTS recommended — available free on
[Oracle Cloud Always Free](https://www.oracle.com/cloud/free/) or from ~$4/month on
Hetzner/DigitalOcean).

The stack uses **Gunicorn** behind **Nginx**, **Supervisor** to keep Celery running, and
**Certbot** for HTTPS.

### 1. Provision the server

```bash
ssh root@YOUR_SERVER_IP
```

```bash
# On the server — install system dependencies
apt update && apt upgrade -y
apt install -y python3.12 python3.12-venv python3-pip \
               postgresql postgresql-contrib \
               redis-server nginx supervisor certbot python3-certbot-nginx \
               git
```

### 2. Create a database and user

```bash
sudo -u postgres psql <<SQL
CREATE DATABASE chantiermobile;
CREATE USER chantiermobile WITH PASSWORD 'choose-a-strong-password';
ALTER ROLE chantiermobile SET client_encoding TO 'utf8';
ALTER ROLE chantiermobile SET default_transaction_isolation TO 'read committed';
ALTER ROLE chantiermobile SET timezone TO 'Africa/Kigali';
GRANT ALL PRIVILEGES ON DATABASE chantiermobile TO chantiermobile;
SQL
```

### 3. Clone the repo and install dependencies

```bash
git clone https://github.com/monsieurpapa/chantierMobile.git /srv/chantiermobile
cd /srv/chantiermobile

python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example /srv/chantiermobile/.env.prod
nano /srv/chantiermobile/.env.prod
```

Minimum production `.env.prod`:

```env
SECRET_KEY=replace-with-a-long-random-string
DEBUG=0
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DATABASE_URL=postgresql://chantiermobile:choose-a-strong-password@localhost:5432/chantiermobile
REDIS_URL=redis://localhost:6379/0
```

### 5. Build the app

```bash
cd /srv/chantiermobile
source venv/bin/activate
export $(cat .env.prod | xargs)

python manage.py collectstatic --no-input
python manage.py migrate
python manage.py createsuperuser
```

### 6. Configure Gunicorn via Supervisor

Create `/etc/supervisor/conf.d/chantiermobile.conf`:

```ini
[program:chantiermobile-web]
command=/srv/chantiermobile/venv/bin/gunicorn chantiermobile.wsgi:application
        --bind unix:/run/chantiermobile.sock
        --workers 3
        --timeout 120
directory=/srv/chantiermobile
user=www-data
environment=SECRET_KEY="%(ENV_SECRET_KEY)s",DEBUG="0",
            DATABASE_URL="%(ENV_DATABASE_URL)s",
            REDIS_URL="%(ENV_REDIS_URL)s",
            ALLOWED_HOSTS="%(ENV_ALLOWED_HOSTS)s"
autostart=true
autorestart=true
stderr_logfile=/var/log/chantiermobile/web.err.log
stdout_logfile=/var/log/chantiermobile/web.out.log

[program:chantiermobile-celery-worker]
command=/srv/chantiermobile/venv/bin/celery -A chantiermobile worker --loglevel=info
directory=/srv/chantiermobile
user=www-data
environment=SECRET_KEY="%(ENV_SECRET_KEY)s",DEBUG="0",
            DATABASE_URL="%(ENV_DATABASE_URL)s",
            REDIS_URL="%(ENV_REDIS_URL)s"
autostart=true
autorestart=true
stderr_logfile=/var/log/chantiermobile/celery-worker.err.log
stdout_logfile=/var/log/chantiermobile/celery-worker.out.log

[program:chantiermobile-celery-beat]
command=/srv/chantiermobile/venv/bin/celery -A chantiermobile beat --loglevel=info
        --scheduler django_celery_beat.schedulers:DatabaseScheduler
directory=/srv/chantiermobile
user=www-data
environment=SECRET_KEY="%(ENV_SECRET_KEY)s",DEBUG="0",
            DATABASE_URL="%(ENV_DATABASE_URL)s",
            REDIS_URL="%(ENV_REDIS_URL)s"
autostart=true
autorestart=true
stderr_logfile=/var/log/chantiermobile/celery-beat.err.log
stdout_logfile=/var/log/chantiermobile/celery-beat.out.log
```

```bash
mkdir -p /var/log/chantiermobile
chown www-data:www-data /var/log/chantiermobile
# Load env vars for supervisor (add to /etc/supervisor/supervisord.conf or use a wrapper)
supervisorctl reread && supervisorctl update
supervisorctl start all
```

### 7. Configure Nginx

Create `/etc/nginx/sites-available/chantiermobile`:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location /static/ {
        alias /srv/chantiermobile/staticfiles/;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://unix:/run/chantiermobile.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

```bash
ln -s /etc/nginx/sites-available/chantiermobile /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
```

### 8. Enable HTTPS with Certbot

```bash
certbot --nginx -d yourdomain.com -d www.yourdomain.com
# Certbot edits the Nginx config and sets up auto-renewal
```

### 9. Deploying updates

```bash
cd /srv/chantiermobile
git pull origin main
source venv/bin/activate
export $(cat .env.prod | xargs)
pip install -r requirements.txt
python manage.py migrate --no-input
python manage.py collectstatic --no-input
supervisorctl restart chantiermobile-web chantiermobile-celery-worker chantiermobile-celery-beat
```

### Supervisor quick-reference

```bash
supervisorctl status                        # Show all process states
supervisorctl restart chantiermobile-web    # Restart web only
supervisorctl tail -f chantiermobile-web    # Live logs
```

## Environment variables reference

All configuration is environment-driven. The defaults in `docker-compose.yml` work for
local development out of the box.

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(insecure dev key)* | Django secret key — **always override in production** |
| `DEBUG` | `0` | Set to `1` for development only — never in a reachable environment |
| `ALLOWED_HOSTS` | `` | Comma-separated list of allowed hostnames |
| `DB_ENGINE` | `django.db.backends.sqlite3` | Switch to `django.db.backends.postgresql` for Postgres |
| `DB_NAME` | `db.sqlite3` | Database name |
| `DB_USER` | `` | Database user |
| `DB_PASSWORD` | `` | Database password |
| `DB_HOST` | `` | Database host |
| `DB_PORT` | `` | Database port |
| `DATABASE_URL` | — | Single connection-string alternative to the `DB_*` vars (Render/Railway style) |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL (used by Celery) |

See `.env.example` for the complete, current list including email and media-storage
(Cloudflare R2) settings.

## Pre-deploy checklist

- [ ] `DEBUG=0`
- [ ] `SECRET_KEY` is a long random value, not the dev default
- [ ] `ALLOWED_HOSTS` matches the real domain(s)
- [ ] `DATABASE_URL` / `REDIS_URL` point at production services, not localhost
- [ ] `python manage.py migrate` run against the target database
- [ ] `python manage.py collectstatic --no-input` run (or handled by `build.sh` / the
  platform's build step)
- [ ] Email backend configured (password reset depends on it — see
  [`docs/security.md`](../security.md#authentication))
- [ ] `just test` passes with ≥80% coverage before merging to `main`
