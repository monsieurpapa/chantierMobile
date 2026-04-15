#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt
# .mo files are committed to git — skip compilemessages (requires gettext, not available on Render)
python manage.py collectstatic --no-input
python manage.py migrate
