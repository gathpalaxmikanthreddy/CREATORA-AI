# Creatora AI data model

This note describes the SQLAlchemy model. Oracle Database is supported through `DATABASE_URL` using python-oracledb; PostgreSQL and local SQLite are also supported.

## People and creator profiles

- **User** stores display/account name, unique email, a local password hash, email-verification state, optional Supabase Auth UUID, role (`creator`, `brand`, or `admin`), active state, creation/update times, and a demo-data marker. New local-password accounts must verify their email before login; existing accounts are marked verified by the additive schema upgrade. With Supabase enabled, passwords and email confirmation are managed by Supabase Auth.
- **CreatorProfile** belongs one-to-one to a user. It holds headline, biography, location, availability, primary specialization, starting price, and external profile link.
- **Specialization**, **ContentType**, **Skill**, and **Tool** are canonical lookup records. Profile-to-specialization/content-type/skill/tool and portfolio-to-skill/tool are many-to-many association tables, so search uses normalized values rather than searching comma-separated text. The old text skill/tool columns remain for backward compatibility.
- **PortfolioItem** belongs to a creator profile. It records title, description, media type, specialization, optional preview/project links, project role, workflow summary, format, aspect ratio, year, commercial-use note, and related normalized skills/tools. Direct MP4, WebM, and Ogg links play inline for video/animation items; other preview images and external work links remain supported. Media is externally hosted rather than uploaded to this prototype.
- **VerificationRecord** identifies a claim by `subject_type` and `subject_id`, with claim category, `unverified`/`pending`/`verified` status, evidence note/reference, reviewer, review time, and demo marker. Its subject reference is polymorphic and is not a database foreign key; the application and seed process scope records by type and ID. Seeded verification signals are fictional, labeled as demo samples, and do not imply real verification.

## Briefs and work

- **Brief** belongs to a brand user and stores campaign title, goal, audience, description, requirements, style, content type, deliverables, format, aspect ratio, duration, quantity, budget, timeline, deadline, and lifecycle status (`draft`, `open`, `paused`, `closed`, `completed`).
- Licensing/usage fields are `commercial_use`, `usage_duration`, `territory`, `exclusivity`, and `allow_edits`. These express the brief's requested terms only, not legal advice. Required skills, specializations, and preferred tools use normalized many-to-many lookup links.
- **Application** joins one creator to one brief, includes proposal text, status, and timestamps. A unique constraint prevents duplicate applications by the same creator to the same brief.
- **Engagement** is created on brand acceptance and has a unique link to that application. Its status tracks accepted, in-progress, submitted, revision-requested, approved, or completed states.
- **Delivery** stores a submitted URL, note, feedback, revision number, state, submitter, and timestamp. New delivery rows keep a revision trail; **EngagementEvent** records the actor, event, note, and time for history.

## Persistence and migration

Without `DATABASE_URL`, SQLite is stored at `instance/marketplace.db`. Configure `DATABASE_URL` with an `oracle+oracledb://` SQLAlchemy URL to store marketplace data in Oracle; `postgresql://` URLs are also supported. Startup initialization calls `create_all` for missing tables and adds columns to earlier prototype tables without dropping existing tables or records. Changing the connection URL does not copy data from another database; back up and migrate existing content separately.

Filterable attributes use lookup tables and joins. Profile `skills` / `tools` legacy text is retained only for compatibility and is not the search index. Portfolio tools/skills also contribute to creator directory matches.
