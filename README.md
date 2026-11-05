# CampusConnect - College Notice & Event Portal

A simple web portal where admins publish notices and events, and students register for events and post lost & found items.

**Stack:** HTML + CSS (light theme) · Python · Flask · SQLite

## Features
- Student registration and login, admin login (role-based access)
- Notice board with categories (admin: add / edit / delete)
- Events with online registration (admin sees the registration list)
- Lost & Found board (post, mark resolved, delete)
- Search across notices, events and items

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000

**Default admin login:** `admin@campus.com` / `admin123`
(Change it with the `ADMIN_EMAIL` and `ADMIN_PASSWORD` environment variables before the first run.)

## Deploy on Render (free)
1. Push this folder to a GitHub repository.
2. On https://render.com choose **New > Web Service** and connect the repo.
3. Settings:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app`
4. Add environment variables: `SECRET_KEY` (any long random text), `ADMIN_EMAIL`, `ADMIN_PASSWORD`.
5. Deploy. Render gives you a public URL.

**Note:** On the free tier the disk is erased on each restart/redeploy, so SQLite data resets
(the admin account is recreated automatically). For permanent data, attach a persistent disk and set
`DATABASE_PATH` to a path on it, or move to a hosted database such as Neon (PostgreSQL).
Deployment steps on PythonAnywhere also work: upload the files and point the WSGI file to `app`.

## Project structure
```
app.py               Flask app: routes, database, auth
templates/           HTML pages (Jinja2)
static/style.css     Light theme styles
requirements.txt     Dependencies
Procfile             Start command for hosting platforms
```

## Suggested team split
- Member 1: templates and CSS (frontend)
- Member 2: routes for notices, events, lost & found, search (backend)
- Member 3: database schema, login/roles, deployment, testing
