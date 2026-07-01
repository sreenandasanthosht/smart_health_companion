# Setup Guide (for complete beginners)

This guide assumes you know almost nothing about Django, MySQL or GitHub.
Follow it top to bottom. It covers: (A) installing tools, (B) putting the
project on GitHub, (C) running it, and (D) working across two laptops.

--------------------------------------------------------------------------
## A. Install the tools (do this once on EACH laptop)

1. **Python 3.11+** — https://www.python.org/downloads/ . During install on
   Windows, tick **"Add Python to PATH"**.
2. **Git** — https://git-scm.com/downloads . This is the tool that talks to
   GitHub.
3. **MySQL** — install **MySQL Community Server** and **MySQL Workbench**
   from https://dev.mysql.com/downloads/ . Remember the **root password** you
   set during installation — you will need it.
4. A code editor — **VS Code** (https://code.visualstudio.com/) is easiest.

Check they installed correctly (open a terminal / Command Prompt):
```
python --version
git --version
```

--------------------------------------------------------------------------
## B. Put the project on GitHub (do this ONCE, on laptop 1)

GitHub is a website that stores your code online so both laptops (and both
teammates) can share it. A "repository" (repo) is one project's folder on
GitHub.

### B1. Create an empty repo on the GitHub website
1. Log in at https://github.com .
2. Click the **+** (top right) -> **New repository**.
3. Repository name: `smart_health_companion`.
4. Choose **Private** (or Public).
5. **Do NOT** tick "Add a README" / .gitignore / license — we already have them.
6. Click **Create repository**. GitHub shows you a page with a URL like
   `https://github.com/YOUR-USERNAME/smart_health_companion.git` — keep it.

### B2. Connect this project folder to that repo (in a terminal, inside the project folder)
```
git init
git add .
git commit -m "Initial Django project skeleton (MVT + MySQL)"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/smart_health_companion.git
git push -u origin main
```
The first push will ask you to sign in to GitHub (a browser window opens, or
it asks for a username + a Personal Access Token). Follow the prompts once and
Git remembers you.

> If we (the assistant) already ran `git init` and made the first commit for
> you, skip the `init/add/commit` lines and just run the last three
> (`branch`, `remote add`, `push`).

--------------------------------------------------------------------------
## C. Run the project (on either laptop)

1. **Open the project folder** in a terminal.
2. **Create a virtual environment** (an isolated box for this project's
   Python packages) and activate it:
   ```
   python -m venv venv
   # Windows:
   venv\Scripts\activate
   # Mac/Linux:
   source venv/bin/activate
   ```
   You'll see `(venv)` at the start of the prompt when it's active.
3. **Install the packages**:
   ```
   pip install -r requirements.txt
   ```
   If `mysqlclient` fails to install on Windows, the easy alternative is:
   `pip install pymysql` and tell us — we'll add one line so it works.
4. **Create the MySQL database.** Open MySQL Workbench (or the MySQL command
   line) and run:
   ```sql
   CREATE DATABASE smart_health_companion CHARACTER SET utf8mb4;
   ```
5. **Make your local config file**:
   ```
   copy .env.example .env      (Windows)   /   cp .env.example .env   (Mac/Linux)
   ```
   Open `.env` and set `DB_PASSWORD` to your MySQL root password.
   (To skip MySQL for a quick test, set `USE_SQLITE=1` instead.)
6. **Create the database tables** from our models:
   ```
   python manage.py makemigrations
   python manage.py migrate
   ```
7. **Create the single admin** (the Django superuser):
   ```
   python manage.py createsuperuser
   ```
8. **Start the server**:
   ```
   python manage.py runserver
   ```
   Open http://127.0.0.1:8000/ — you should see the dummy home page.
   The admin panel is at http://127.0.0.1:8000/admin/ .

--------------------------------------------------------------------------
## D. Working across two laptops (or two teammates)

The golden rule: **share code through GitHub, not by copying folders.**

### First time on the SECOND laptop
```
git clone https://github.com/YOUR-USERNAME/smart_health_companion.git
cd smart_health_companion
```
Then do Section C (venv, install, create DB, .env, migrate, runserver).
Note: `.env` and the database are NOT shared (they hold local secrets/data) —
each laptop makes its own. The code and the migration files ARE shared.

### Every working session (both laptops)
Start of the day — get the latest code:
```
git pull origin main
```
After you make changes — save them and send them up:
```
git add .
git commit -m "describe what you changed"
git push origin main
```
Then the other laptop runs `git pull` to receive them.

### If you changed models (added/edited a table)
After `git pull`, also run:
```
python manage.py migrate
```
so your local database matches the new code.

> Tip: avoid both laptops editing the same file at the same time. If Git
> reports a "merge conflict", pull first, resolve, then push. Ask us if that
> happens — it's normal and fixable.
