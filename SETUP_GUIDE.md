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

--------------------------------------------------------------------------
## E. Switching your laptop from SQLite to MySQL

MySQL is the database we are using for CareNest. If your `.env` currently
says `USE_SQLITE=1`, you have been running on a local test file
(`db.sqlite3`) instead. Follow this once to move over. Nothing about the
code changes — only your own machine.

### E1. Install MySQL (if you have not)
Install **MySQL Community Server** + **MySQL Workbench** from
https://dev.mysql.com/downloads/ . Write down the **root password** you set
during the installer — you cannot recover it later.

Check it worked: open MySQL Workbench and connect to the local instance.

### E2. Create the empty database
In MySQL Workbench (or `mysql -u root -p` at a Command Prompt), run:
```sql
CREATE DATABASE smart_health_companion CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```
Only the empty database is created by hand. Every table inside it is built
by Django in step E4 — never create tables manually.

### E3. Point your `.env` at MySQL
Open `.env` (the real one, not `.env.example`) and change exactly two lines:
```
DB_PASSWORD=<the MySQL root password from E1>
USE_SQLITE=0
```
Leave `DB_NAME`, `DB_USER`, `DB_HOST`, `DB_PORT` as they are. `.env` is
gitignored, so your password is never pushed to GitHub.

### E4. Build the tables
```
venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
```
If `pip install mysqlclient` fails on Windows, run `pip install pymysql`
instead — the project already falls back to it automatically
(see `config/__init__.py`).

Do **not** run `makemigrations` here. The migration files in `accounts/`,
`health/`, `providers/` etc. are already in Git and are the shared schema;
`migrate` replays them into your fresh MySQL database.

### E5. Fill it with demo data
```
python manage.py seed_demo
python manage.py createsuperuser
python manage.py runserver
```
`seed_demo` creates one account per role with realistic history, so every
page has something to show. The demo password is in
`core/management/commands/seed_demo.py`.

### E6. (Optional) Carry your old SQLite data across
Only do this if there is something in `db.sqlite3` you want to keep.
Otherwise skip it — `seed_demo` gives you a cleaner starting point.

With `.env` still on `USE_SQLITE=1`:
```
python manage.py dumpdata --natural-foreign --natural-primary ^
  -e contenttypes -e auth.permission -e sessions ^
  --indent 2 -o sqlite_backup.json
```
Then set `USE_SQLITE=0`, run `python manage.py migrate`, and load it:
```
python manage.py loaddata sqlite_backup.json
```
(`^` is the Windows line-continuation character. Put it all on one line if
you prefer.) Do not commit `sqlite_backup.json`.

--------------------------------------------------------------------------
## F. What "the same database" does and does not mean

We each run our own MySQL server on our own laptop. Two different things get
shared, and it is worth being clear about which is which:

| Thing | Shared? | How |
|---|---|---|
| Table structure (the schema) | **Yes** | Migration files in Git |
| Demo/seed data | **Yes, equivalently** | Both run `python manage.py seed_demo` |
| Rows you type in while testing | **No** | They live only in your own MySQL |
| `.env` (passwords, API keys) | **No** | Each laptop has its own |

So if Terese registers a patient on her laptop, Sreenanda will not see that
patient — but she will have the exact same tables and the same seeded
accounts. That is the normal, intended setup: real projects keep developer
databases separate so one person's experiment cannot corrupt the other's work.

If we ever need one genuinely shared live database (for a joint demo, or for
the final submission), we point both `.env` files at one hosted MySQL
instance instead of `127.0.0.1`. Nothing else changes.

### The one rule that keeps our schemas identical
**Only one person runs `makemigrations` for any given model change.**

1. Whoever edits `models.py` runs `python manage.py makemigrations`.
2. They commit the generated migration file **together with** the model change.
3. The other person runs `git pull` then `python manage.py migrate` — and
   nothing else.

If both of you run `makemigrations` for the same change, Git ends up with two
migration files describing one change and the next merge needs a
`makemigrations --merge` to untangle it. (We already have a few of those in
the history — `0009_merge_...`, `0006_merge_...` — which is why this rule is
here.)

--------------------------------------------------------------------------
## G. Sharing DATA between the two laptops

Section F explained that our two MySQL databases are separate. This section
is how we keep the *contents* in step anyway. There are two ways, and it
matters which one you reach for.

### G1. The normal way — `seed_demo` (prefer this)

`core/management/commands/seed_demo.py` builds the demo world in code: one
account per role, weeks of vitals and medication history, verified and
pending providers, appointments, caregiver links, consent grants, a nursing
assignment. Running it is safe any number of times — it looks accounts up by
email and tops up what is missing instead of duplicating.

```
python manage.py seed_demo
```

**When you add data the project should always have** — a new provider
specialty, a new role's demo account, a scenario a page needs in order to
look right — add it to `seed_demo.py`, commit it, and push. The other person
runs `git pull` then `python manage.py seed_demo` and now has it too.

This is the method to reach for by default. It is code, so Git merges it
sensibly, it is reviewable in a pull request, and it can never collide.

### G2. The occasional way — `export_data` (hand-made state)

Sometimes you have clicked a lot of things into the running app and want to
hand over *that exact state* rather than re-type it into `seed_demo.py`.

On the laptop that has the data:
```
python manage.py export_data
git add seed_data/shared_data.json
git commit -m "Share current database state"
git push
```

On the other laptop:
```
git pull
python manage.py loaddata seed_data/shared_data.json
```

**Read this before using it.** `loaddata` matches rows by primary key and
overwrites them. If you have both been creating records independently, your
row #7 and her row #7 are different things, and loading her file on top of
your populated database silently replaces yours. So:

- Only one person exports — whoever has the state worth keeping.
- The other person loads it into a database with nothing to lose: freshly
  migrated, or after `python manage.py flush`.

Treat the file as a **snapshot handover**, never as a merge.

### G3. Which to use

| Situation | Use |
|---|---|
| New demo content the project should always have | `seed_demo.py` (G1) |
| Starting a fresh database on either laptop | `migrate` then `seed_demo` |
| Handing over hand-clicked state one time | `export_data` (G2) |
| Both of you have data you want to keep | Neither — pick one as the source, the other flushes |

### G4. Starting completely fresh (either laptop, any time)

```
python manage.py flush          # empties the tables, keeps the structure
python manage.py seed_demo
python manage.py createsuperuser
```
If the structure itself is wrong, drop and recreate the database in MySQL
Workbench and run `migrate` again — never edit tables by hand.
