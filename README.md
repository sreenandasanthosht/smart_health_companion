# Smart Health Companion

An Intelligent Integrated Health Management Ecosystem — MDS482-4 Project-I.
Built with **Django** (Python) using the **MVT** architecture and **MySQL**.

## Project layout

```
smart_health_companion/
├── manage.py            # command tool
├── config/              # project settings + top-level URLs
├── accounts/            # app: users, roles, unique id, login
├── health/              # app: vitals, medications, lifestyle, mental health
├── providers/           # app: listings, appointments, notes
├── core/                # app: home page + dashboards (the dummy page lives here)
├── templates/base.html  # shared Bootstrap layout
└── static/              # CSS / JS / images
```

One **project** (`smart_health_companion`), four **apps** (`accounts`, `health`,
`providers`, `core`). In Django an "app" is a feature-module, not the whole site.

## Quick start (short version — full steps in SETUP_GUIDE.md)

```bash
# 1. create & activate a virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# 2. install dependencies
pip install -r requirements.txt

# 3. set up your local config
cp .env.example .env            # Windows: copy .env.example .env
#   then edit .env with your MySQL password
#   (or set USE_SQLITE=1 in .env to test without MySQL)

# 4. create the database tables
python manage.py makemigrations
python manage.py migrate

# 5. create the single admin (Django superuser)
python manage.py createsuperuser

# 6. run it
python manage.py runserver
# open http://127.0.0.1:8000/  -> you should see the dummy home page
# admin panel: http://127.0.0.1:8000/admin/
```
