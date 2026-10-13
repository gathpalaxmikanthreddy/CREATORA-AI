# Creatora AI

A local Flask prototype for an AI-native creator marketplace: AI portfolios, creator discovery, campaign briefs, applications, and a delivery/revision workflow. The interface uses local CSS/JavaScript and does not need remote fonts, images, paid services, or an AI API key.

## Evaluation priorities

| Challenge criterion | Status in this prototype |
| --- | --- |
| Creator profiles and AI portfolios (30%) | Implemented: creator profiles plus linked AI work, previews/direct video playback, tools/models, skills, specializations, workflow, format, and usage notes. |
| Creator discovery and filtering (25%) | Implemented: combined search and filters for skills, specialization, tools, content type, location, and availability, with result counts and an empty-state/clear-filters path. |
| Brand brief definition (20%) | Implemented: drafts, publishing, campaign requirements, deliverables, content type, style, format/aspect ratio, budget, and usage/licensing fields. |
| User experience (15%) | Implemented: separate brand and creator paths, responsive pages, profile/portfolio details, and application-to-delivery/revision states. |
| Presentation/demo (10%) | Included: [DEMO_SCRIPT.md](./DEMO_SCRIPT.md) provides a timed walkthrough and judge outline; [DATA_MODEL.md](./DATA_MODEL.md) documents the schema. |
| AI-assisted brief builder (bonus) | Partial: the no-key builder suggests editable fields using transparent local rules. It is not an LLM and does not claim model-generated results. |
| Creator verification signals (bonus) | Demonstrated: tools/workflow/past-work statuses are visible. Seeded examples are fictional and clearly marked **Demo sample**, not real verification. |

## Requirements and first run

Python 3.10+ is recommended. On Windows PowerShell, from the project directory:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Replace `SECRET_KEY` in your local `.env` with a private random value before using the app beyond a local demo. Do not commit `.env`. Without `DATABASE_URL`, the app stores data in SQLite at `instance/marketplace.db`; keep `COOKIE_SECURE=0` for local HTTP. Set it to `1` only when serving through HTTPS.

## Email verification

Local-password registrations require email verification by default. Configure an SMTP sender in `.env` before registering:

```env
EMAIL_VERIFICATION_REQUIRED=1
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
SMTP_USE_TLS=1
SMTP_USE_SSL=0
MAIL_FROM=Creatora AI <no-reply@example.com>
PUBLIC_BASE_URL=http://127.0.0.1:5000
EMAIL_VERIFICATION_MAX_AGE=86400
PASSWORD_RESET_MAX_AGE=3600
```

Use the SMTP host, port, username, and password from your email provider (for Gmail, use a 16-character Google App Password rather than your Google sign-in password), not your Neon database credentials. If you paste a Gmail App Password with its displayed grouping spaces, the app removes those spaces before authenticating and reports a configuration error if the resulting value is not 16 characters. Use `SMTP_USE_TLS=1` for STARTTLS (typically port 587), or set `SMTP_USE_TLS=0` and `SMTP_USE_SSL=1` for implicit TLS (typically port 465). Do not enable both. Set `PUBLIC_BASE_URL` to the exact public HTTPS origin when deployed. Verification links expire after 24 hours by default; users can request a new link from the login page. Never commit `.env` or share SMTP credentials.

The login page includes a **Forgot password?** link. Local-password accounts receive a signed, one-use reset link by SMTP; configure the same SMTP settings and `PUBLIC_BASE_URL` above. Reset links expire after one hour by default (`PASSWORD_RESET_MAX_AGE`). When Supabase Auth is enabled, recovery email is sent by Supabase and redirects to the app reset page; add that URL to the Supabase Auth redirect allow list.

## Oracle Database

To use Oracle, set `DATABASE_URL` in `.env` to an Oracle SQLAlchemy connection URL. Oracle Database 12c or newer is recommended for identity columns:

```env
DATABASE_URL=oracle+oracledb://APP_USER:URL_ENCODED_PASSWORD@HOST:1521/?service_name=SERVICE_NAME
```

Replace the example username, password, host, port, and service name with your database connection details. URL-encode special characters in the password. The included `oracledb` driver uses python-oracledb's Thin mode by default, so Oracle Instant Client is not required for standard connections.

Then install dependencies and initialize the schema:

```powershell
python -m pip install -r requirements.txt
flask --app app init-db
python app.py
```

`init-db` creates missing tables and applies the app's additive legacy-column updates. It does not copy records from an existing SQLite or PostgreSQL database; migrate existing data separately before switching databases. Supabase Auth can optionally remain enabled for authentication by setting both `SUPABASE_URL` and `SUPABASE_KEY`; leave both empty to use local password authentication with Oracle-backed marketplace data.

## Supabase Auth and Postgres (optional)

The app uses local SQLite/password authentication when Supabase settings are empty. To use Supabase:

1. Create a Supabase project and enable **Authentication → Sign In / Providers → Email**.
2. In **Project Settings → API Keys**, copy the Project URL and a publishable key (or legacy anon key). Never use the `service_role`/secret key in this Flask app.
3. In the Supabase project’s **Connect** dialog, copy a Postgres connection string. Prefer the direct connection when your network supports IPv6, or the session pooler for networks that do not. Keep the database password private and URL-encode special characters in it.
4. Put the values in your local `.env` (do not paste them into source code or commit `.env`):

   ```env
   DATABASE_URL=postgresql://postgres:URL_ENCODED_PASSWORD@YOUR_DB_HOST:5432/postgres?sslmode=require
   SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
   SUPABASE_KEY=YOUR_PUBLISHABLE_OR_ANON_KEY
   ```

   The app converts `postgresql://` to the included psycopg 3 driver URL. You can use `SUPABASE_PUBLISHABLE_KEY` or `SUPABASE_ANON_KEY` instead of `SUPABASE_KEY`. Set both Supabase values, or leave both empty to use local authentication.
5. Install the updated dependencies and initialize the selected database:

   ```powershell
   python -m pip install -r requirements.txt
   flask --app app init-db
   python app.py
   ```

6. Register and log in using the app. If Supabase email confirmation is enabled, follow the confirmation email before logging in. Logout clears the Flask app session.
7. For a populated showcase on a new/empty database, run `flask --app app seed-demo`. Demo records are clearly labeled; seeded demo passwords are for local authentication only. With Supabase Auth enabled, create/sign in to Supabase Auth accounts through the registration page rather than expecting the seed command to create Auth users.

Supabase Auth stores credentials; the marketplace `users` table stores the app profile and links it by Supabase Auth user ID. The old SQLite account password hashes are not imported into Supabase Auth. A legacy local account can be linked after signing in through Supabase with its **verified matching email**. Existing SQLite marketplace content is not automatically copied to Postgres; keep the SQLite file as a backup and plan a separate data migration if needed. Never send database passwords or Supabase keys to chat.

Create/upgrade the database and run the app:

```powershell
flask --app app init-db
python app.py
```

Open <http://127.0.0.1:5000>. The app also performs the additive schema setup on startup. It creates missing tables and adds missing columns; it does not drop tables or clear user records. Back up `instance/marketplace.db` before manual schema changes.

Run the automated workflow tests from the project directory:

```powershell
python -m unittest discover -s tests -v
```

## Demo data

Seed believable, clearly marked showcase content without resetting the database:

```powershell
flask --app app seed-demo
```

The command is idempotent for its demo records and refuses to take over an existing non-demo account with a colliding seed email. It adds 6 creator profiles with two portfolio entries each, a brand account, four briefs, applications in multiple states, delivery/revision examples, and explicitly labeled demo verification records.

New local demo accounts use **`CreatorDemo!2026`** unless `DEMO_PASSWORD` or `--password` is supplied. Seed-created logins:

- Brand: `brand@demo.creatora.test`
- Creators: `mira@demo.creatora.test`, `arjun@demo.creatora.test`, `zoya@demo.creatora.test`, `kabir@demo.creatora.test`, `leela@demo.creatora.test`, `dev@demo.creatora.test`

Use the seeded password for these accounts only on a local demo instance. Do not use it in a deployed environment. The script will not overwrite an existing account password or delete data.

## Account roles

Creatora supports creator, brand, and admin accounts. Admins can use `/admin/login` and the protected `/admin` dashboard to view platform counts and search/filter the account directory. Registration does not allow users to select the admin role. To create a local-password admin, run `flask --app app create-admin` from the project directory and enter credentials at the hidden prompts. For an existing active, email-verified account, run `flask --app app promote-admin your-account@example.com`. When Supabase Auth is enabled, register and confirm the account in the app before promoting it; `create-admin` is intentionally disabled in Supabase mode. Both commands operate on the database configured by `DATABASE_URL`.

## Main flows

- Register/login as a creator or brand; local-password registrations require an email confirmation before login, and passwords are stored as Werkzeug password hashes.
- Creators maintain a searchable profile and add AI portfolio items with media type, tools/models, skills, workflow, format, rights note, and external preview links.
- Brands combine creator search terms and multi-select filters for skills, specializations, tools, content type, location, and availability.
- Brands create/edit/save/publish briefs, pause/close them, and use a local rules-based idea-to-brief suggestion flow.
- Creators apply to open briefs. Brands shortlist, accept, or decline; acceptance opens a private engagement workspace.
- Creators start accepted work and submit a delivery URL and note. Brands request revisions or approve; creators resubmit, and brands can mark approved work complete.
- Private routes and state-changing actions check role/ownership. POST forms use Flask-WTF CSRF protection.

The local brief builder is transparent rules-based assistance, not an LLM. Verification statuses are distinct; seed examples are marked **Demo sample** and are not evidence of real-world verification. Portfolio uploads are not stored by this prototype: creators may enter an optional preview/work link (direct MP4, WebM, and Ogg links play inline for video/animation), and delivery is a link plus note.

## Structure

- `app.py`, `models.py`, `seed_demo.py`: routes, data model, safe demo-data command.
- `templates/`: shared layout and marketplace pages.
- `static/css/style.css`, `static/js/app.js`: local UI assets.
- `.env.example`: safe local configuration template.
- `DATA_MODEL.md`: entity and relationship summary.
- `DEMO_SCRIPT.md`: timed demo and presentation outline.
- `instance/marketplace.db`: local SQLite database when SQLite is selected; ignored by Git.

`venv/`, `.env`, `instance/`, `__pycache__/`, and Python bytecode are ignored. Install from `requirements.txt` in a clean virtual environment.

## Known prototype limits

- No binary upload/storage, messaging service, payment flow, notifications, AI-provider integration, or verification-review screen.
- Verification sample records exist solely to demonstrate status display; seeded evidence is fictional and visibly labeled.
- Licensing fields express brief requirements only and are not legal advice.
- The included automated suite covers the core account, discovery, brief, application, delivery, revision, and ownership flows. Use `DEMO_SCRIPT.md` to exercise the visual experience in a browser.
