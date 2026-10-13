import os
import re
import secrets
import smtplib
import ssl
from datetime import date
from email.message import EmailMessage
from functools import wraps
from urllib.parse import urlsplit

import click
import httpx
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFError, CSRFProtect
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import Boolean, inspect, or_, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateIndex
from supabase import create_client
from supabase_auth.errors import AuthError
from werkzeug.security import check_password_hash, generate_password_hash

from models import (
    Application,
    Brief,
    ContentType,
    CreatorProfile,
    Delivery,
    Engagement,
    EngagementEvent,
    PortfolioItem,
    Skill,
    Specialization,
    Tool,
    User,
    VerificationRecord,
    db,
)
from seed_demo import register_seed_command


basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))

app = Flask(__name__, instance_relative_config=True)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["EMAIL_VERIFICATION_REQUIRED"] = os.getenv(
    "EMAIL_VERIFICATION_REQUIRED", "1"
).strip() == "1"
app.config["SMTP_HOST"] = os.getenv("SMTP_HOST", "").strip()
app.config["SMTP_PORT"] = int(os.getenv("SMTP_PORT", "587"))
app.config["SMTP_USERNAME"] = os.getenv("SMTP_USERNAME", "").strip()
app.config["SMTP_PASSWORD"] = os.getenv("SMTP_PASSWORD", "")
app.config["SMTP_USE_TLS"] = os.getenv("SMTP_USE_TLS", "1").strip() == "1"
app.config["SMTP_USE_SSL"] = os.getenv("SMTP_USE_SSL", "0").strip() == "1"
app.config["MAIL_FROM"] = os.getenv("MAIL_FROM", "").strip()
app.config["PUBLIC_BASE_URL"] = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
app.config["EMAIL_VERIFICATION_MAX_AGE"] = int(
    os.getenv("EMAIL_VERIFICATION_MAX_AGE", "86400")
)
app.config["PASSWORD_RESET_MAX_AGE"] = int(
    os.getenv("PASSWORD_RESET_MAX_AGE", "3600")
)
database_url = os.getenv("DATABASE_URL", "sqlite:///marketplace.db").strip()

# Strip wrapping quotes that break URL parsing on platforms like Render
if (database_url.startswith('"') and database_url.endswith('"')) or (
    database_url.startswith("'") and database_url.endswith("'")
):
    database_url = database_url[1:-1].strip()

if not database_url:
    raise RuntimeError(
        "DATABASE_URL is set but empty. Provide a valid database connection "
        "string or remove the variable to use the SQLite fallback."
    )

if database_url.startswith("postgres://"):
    database_url = "postgresql://" + database_url.removeprefix("postgres://")
if database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url.removeprefix(
        "postgresql://"
    )
if database_url.startswith("oracle://"):
    database_url = "oracle+oracledb://" + database_url.removeprefix("oracle://")
if database_url.startswith("oracle+cx_oracle://"):
    database_url = "oracle+oracledb://" + database_url.removeprefix(
        "oracle+cx_oracle://"
    )

# Validate the URL before handing it to SQLAlchemy so errors are clear
import sqlalchemy as _sa
try:
    _parsed = _sa.engine.make_url(database_url)
    print(f"[startup] Database dialect: {_parsed.drivername}, host: {_parsed.host}")
except Exception as _exc:
    # Show only the start of the value so the password is never leaked
    _preview = database_url[:30] + ("..." if len(database_url) > 30 else "")
    raise RuntimeError(
        f"DATABASE_URL is not a valid SQLAlchemy connection string.\n"
        f"  Preview: {_preview!r}\n"
        f"  Error:   {_exc}\n"
        f"  Hints:   - Remove surrounding quotes from the value\n"
        f"           - URL-encode special characters in the password "
        f"(@ -> %40, # -> %23, / -> %2F)\n"
        f"           - Make sure the URL starts with a valid scheme "
        f"(postgresql://, sqlite:///, oracle://)"
    ) from None

app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SUPABASE_URL"] = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
app.config["SUPABASE_KEY"] = (
    os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
    or ""
).strip()
app.config["SUPABASE_AUTH_ENABLED"] = bool(
    app.config["SUPABASE_URL"] and app.config["SUPABASE_KEY"]
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "connect_args": {
        "connect_timeout": 10,
    },
}
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("COOKIE_SECURE", "0") == "1"
app.config["WTF_CSRF_TIME_LIMIT"] = 3600

if not app.config["SECRET_KEY"]:
    raise RuntimeError("SECRET_KEY is missing. Add it to your .env file.")
if not 1 <= app.config["SMTP_PORT"] <= 65535:
    raise RuntimeError("SMTP_PORT must be between 1 and 65535.")
if app.config["EMAIL_VERIFICATION_MAX_AGE"] <= 0:
    raise RuntimeError("EMAIL_VERIFICATION_MAX_AGE must be a positive number of seconds.")
if app.config["PASSWORD_RESET_MAX_AGE"] <= 0:
    raise RuntimeError("PASSWORD_RESET_MAX_AGE must be a positive number of seconds.")
if bool(app.config["SUPABASE_URL"]) != bool(app.config["SUPABASE_KEY"]):
    raise RuntimeError(
        "Set both SUPABASE_URL and SUPABASE_KEY, or leave both empty."
    )

os.makedirs(app.instance_path, exist_ok=True)
db.init_app(app)
csrf = CSRFProtect(app)
migrate = Migrate(app, db)


def migrate_legacy_columns():
    """Add fields to earlier schemas without dropping any user data."""
    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())
    defaults = {
        ("users", "is_demo"): "0",
        ("users", "auth_user_id"): None,
        ("users", "email_verified"): "1",
        ("creator_profiles", "location"): "''",
        ("creator_profiles", "availability"): "'open'",
        ("creator_profiles", "profile_url"): "''",
        ("portfolio_items", "media_type"): "'video'",
        ("portfolio_items", "specialization"): "''",
        ("portfolio_items", "preview_url"): "''",
        ("portfolio_items", "project_role"): "''",
        ("portfolio_items", "workflow_summary"): "''",
        ("portfolio_items", "format"): "''",
        ("portfolio_items", "aspect_ratio"): "''",
        ("portfolio_items", "commercial_use"): "'Not specified'",
        ("briefs", "goal"): "''",
        ("briefs", "audience"): "''",
        ("briefs", "requirements"): "''",
        ("briefs", "style"): "''",
        ("briefs", "content_type"): "'video'",
        ("briefs", "deliverables"): "''",
        ("briefs", "format"): "''",
        ("briefs", "duration"): "''",
        ("briefs", "quantity"): "1",
        ("briefs", "timeline"): "''",
        ("briefs", "licensing_type"): "'organic_only'",
        ("briefs", "exclusivity"): "'none'",
        ("briefs", "allow_edits"): "0",
        ("briefs", "is_demo"): "0",
    }
    timestamp_columns = {
        "users": ("updated_at",),
        "creator_profiles": ("updated_at",),
        "portfolio_items": ("updated_at",),
        "briefs": ("updated_at",),
        "applications": ("updated_at",),
    }
    for table in db.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        known_columns = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in known_columns or column.primary_key:
                continue
            sql_type = column.type.compile(dialect=db.engine.dialect)
            default = defaults.get((table.name, column.name))
            if isinstance(column.type, Boolean) and default is not None:
                if db.engine.dialect.name == "postgresql":
                    default = {"0": "FALSE", "1": "TRUE"}.get(default, default)
            default_clause = f" DEFAULT {default}" if default is not None else ""
            add_column = (
                f'ALTER TABLE "{table.name}" ADD ("{column.name}" '
                f"{sql_type}{default_clause})"
                if db.engine.dialect.name == "oracle"
                else f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
                f"{sql_type}{default_clause}"
            )
            db.session.execute(
                text(add_column)
            )
        for column_name in timestamp_columns.get(table.name, ()):
            if column_name not in known_columns:
                db.session.execute(
                    text(
                        f'UPDATE "{table.name}" SET "{column_name}" = CURRENT_TIMESTAMP '
                        f'WHERE "{column_name}" IS NULL'
                    )
                )
    db.session.commit()  # release locks before inspecting on another connection

    if "applications" in existing_tables:
        columns = {column["name"] for column in inspect(db.engine).get_columns("applications")}
        if "status" in columns:
            db.session.execute(
                text("UPDATE applications SET status = 'applied' WHERE status = 'pending'")
            )
    if "users" in existing_tables:
        user_columns = {
            column["name"] for column in inspect(db.engine).get_columns("users")
        }
        if "auth_user_id" in user_columns:
            if db.engine.dialect.name == "oracle":
                existing_indexes = {
                    index["name"].lower()
                    for index in inspect(db.engine).get_indexes("users")
                    if index.get("name")
                }
                if "ix_users_auth_user_id" not in existing_indexes:
                    index = next(
                        index
                        for index in User.__table__.indexes
                        if index.name == "ix_users_auth_user_id"
                    )
                    db.session.execute(CreateIndex(index))
            else:
                db.session.execute(
                    text(
                        "CREATE UNIQUE INDEX IF NOT EXISTS "
                        "ix_users_auth_user_id ON users (auth_user_id)"
                    )
                )
    db.session.commit()


def initialize_database():
    db.create_all()
    migrate_legacy_columns()
    for name in ("Video", "Animation", "Image", "Graphics", "Audio", "Other"):
        existing = ContentType.query.filter(
            db.func.lower(ContentType.name) == name.lower()
        ).first()
        if existing is None:
            db.session.add(ContentType(name=name))
    db.session.commit()


class MarketplaceIdentityError(Exception):
    """Raised when a Supabase identity cannot be safely mapped to a local user."""


def supabase_client():
    if not app.config["SUPABASE_AUTH_ENABLED"]:
        raise RuntimeError("Supabase Auth is not configured.")
    return create_client(app.config["SUPABASE_URL"], app.config["SUPABASE_KEY"])


def _auth_value(auth_user, field, default=None):
    if isinstance(auth_user, dict):
        return auth_user.get(field, default)
    return getattr(auth_user, field, default)


def _auth_email_is_confirmed(auth_user):
    return bool(
        _auth_value(auth_user, "email_confirmed_at")
        or _auth_value(auth_user, "confirmed_at")
    )


def supabase_signup_error_message(error, email, password):
    code = getattr(error, "code", None)
    messages = {
        "email_provider_disabled": (
            "Email registration is disabled in Supabase. Enable Email under "
            "Authentication → Sign In / Providers."
        ),
        "signup_disabled": (
            "New registrations are disabled in Supabase Auth. Enable sign-ups "
            "in the Supabase Authentication settings."
        ),
        "email_exists": (
            "An account with this email already exists. Try logging in instead."
        ),
        "user_already_exists": (
            "An account with this email already exists. Try logging in instead."
        ),
        "weak_password": (
            "Supabase rejected this password. Choose a stronger password that "
            "meets your project's password policy."
        ),
        "over_email_send_rate_limit": (
            "Supabase is temporarily limiting confirmation emails. Wait before "
            "trying again, or configure custom SMTP in Supabase."
        ),
        "email_address_not_authorized": (
            "This email cannot receive messages with the current Supabase email "
            "configuration. Configure SMTP or authorize the address for testing."
        ),
        "email_address_invalid": "Enter a valid email address and try again.",
    }
    if code in messages:
        return messages[code]

    detail = str(getattr(error, "message", "") or "").strip()
    for sensitive_value in (email, password):
        if sensitive_value:
            detail = detail.replace(sensitive_value, "[redacted]")
    detail = " ".join(detail.split())[:240]
    if detail:
        return f"Supabase rejected registration: {detail}"
    return "Supabase rejected registration. Check the Supabase Auth settings and try again."


def marketplace_user_for_auth(
    auth_user, *, role_if_new="creator", name_if_new=None, activate=True
):
    auth_user_id = str(_auth_value(auth_user, "id") or "")
    email = str(_auth_value(auth_user, "email") or "").strip().lower()
    if not auth_user_id or not email:
        raise MarketplaceIdentityError(
            "Supabase did not return a user ID and email for this account."
        )

    user = User.query.filter_by(auth_user_id=auth_user_id).first()
    if user is None:
        user = User.query.filter_by(email=email).first()
        if user is not None and user.auth_user_id:
            raise MarketplaceIdentityError(
                "This email is already linked to a different sign-in account."
            )
        if user is not None and not _auth_email_is_confirmed(auth_user):
            raise MarketplaceIdentityError(
                "Confirm your email before linking it to an existing Creatora account."
            )
        if user is None:
            role = role_if_new if role_if_new in {"creator", "brand"} else "creator"
            name = (name_if_new or email.partition("@")[0]).strip()[:100] or "Creator"
            user = User(
                name=name,
                email=email,
                password_hash=generate_password_hash(secrets.token_urlsafe(32)),
                role=role,
                is_active=activate,
                email_verified=_auth_email_is_confirmed(auth_user),
                auth_user_id=auth_user_id,
            )
            if role == "creator":
                user.creator_profile = CreatorProfile(display_name=name)
            db.session.add(user)
        else:
            user.auth_user_id = auth_user_id
    elif user.email != email:
        if User.query.filter(User.email == email, User.id != user.id).first():
            raise MarketplaceIdentityError(
                "This email is already linked to a different Creatora account."
            )
        user.email = email

    user.email_verified = _auth_email_is_confirmed(auth_user)
    if activate:
        user.is_active = True
    if user.role == "creator" and user.creator_profile is None:
        user.creator_profile = CreatorProfile(display_name=user.name)
    db.session.commit()
    return user


@app.template_filter("currency")
def format_currency(amount):
    return f"₹{amount or 0:,.0f}"


@app.template_filter("humanize_status")
def humanize_status(value):
    return (value or "").replace("_", " ").title()


@app.template_filter("direct_video_url")
def is_direct_video_url(value):
    parsed_url = urlsplit(value or "")
    return parsed_url.scheme in {"http", "https"} and parsed_url.path.lower().endswith(
        (".mp4", ".webm", ".ogg")
    )


def parse_csv(value):
    values = (part.strip() for part in (value or "").split(","))
    return list({value.casefold(): value for value in values if value}.values())


def get_or_create_tags(model, values):
    tags = []
    for value in values:
        tag = model.query.filter(db.func.lower(model.name) == value.lower()).first()
        if tag is None:
            tag = model(name=value)
            db.session.add(tag)
        tags.append(tag)
    return tags


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user_id = session.get("user_id")
        user = db.session.get(User, user_id) if user_id else None
        if user is None or not user.is_active:
            session.clear()
            flash("Please log in to continue.", "error")
            return redirect(url_for("login", next=request.path))
        session["user_role"] = user.role
        session["user_name"] = user.name
        return view(*args, **kwargs)

    return wrapped_view


def role_required(role):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped_view(*args, **kwargs):
            if session.get("user_role") != role:
                flash(f"This action is available to {role}s only.", "error")
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped_view

    return decorator


def current_user():
    return db.session.get(User, session["user_id"])


def creator_profile_for(user):
    profile = CreatorProfile.query.filter_by(user_id=user.id).first()
    if profile is None:
        profile = CreatorProfile(display_name=user.name, user=user)
        db.session.add(profile)
        db.session.flush()
    return profile


def safe_next_url(target):
    parsed = urlsplit(target or "")
    return bool(
        target
        and target.startswith("/")
        and not target.startswith("//")
        and "\\" not in target
        and not parsed.scheme
        and not parsed.netloc
    )


def optional_http_url(value, label):
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except ValueError as error:
        raise ValueError(f"Enter a valid {label} URL.") from error
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{label.title()} must start with http:// or https://.")
    return value


def parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("Enter a valid deadline date.")


def brief_form_values(brief=None):
    return {
        field: request.form.get(field, getattr(brief, field, default) if brief else default)
        for field, default in {
            "title": "",
            "goal": "",
            "audience": "",
            "description": "",
            "requirements": "",
            "style": "",
            "content_type": "video",
            "deliverables": "",
            "format": "",
            "aspect_ratio": "",
            "duration": "",
            "category": "Any",
            "budget": 0,
            "quantity": 1,
            "timeline": "",
            "deadline": "",
            "commercial_use": "organic_only",
            "usage_duration": "",
            "territory": "",
            "exclusivity": "none",
            "allow_edits": False,
            "skills": "",
            "specializations": "",
            "tools": "",
            "status": "draft",
        }.items()
    }


def save_brief(brief=None):
    values = brief_form_values(brief)
    errors = []
    required = ("title", "goal", "audience", "description", "content_type", "deliverables")
    for field in required:
        if not str(values[field]).strip():
            errors.append(f"{field.replace('_', ' ').title()} is required.")
    try:
        budget = int(values["budget"])
        quantity = int(values["quantity"])
        deadline = parse_date(values["deadline"])
        if budget < 0 or quantity < 1:
            raise ValueError("Budget cannot be negative and quantity must be at least one.")
    except (ValueError, TypeError) as error:
        errors.append(str(error))
        budget = 0
        quantity = 1
        deadline = None

    if errors:
        return render_template(
            "brief_form.html",
            brief=brief,
            values=values,
            errors=errors,
            content_types=ContentType.query.order_by(ContentType.name).all(),
        ), 400

    if brief is None:
        brief = Brief(brand_id=current_user().id)
        db.session.add(brief)
    for field in (
        "title", "goal", "audience", "description", "requirements", "style",
        "content_type", "deliverables", "format", "aspect_ratio", "duration",
        "category", "timeline", "commercial_use", "usage_duration", "territory",
        "exclusivity",
    ):
        setattr(brief, field, str(values[field]).strip())
    brief.budget = budget
    brief.quantity = quantity
    brief.deadline = deadline
    brief.allow_edits = "allow_edits" in request.form
    brief.status = "open" if request.form.get("publish") == "yes" else "draft"
    brief.required_skills = get_or_create_tags(Skill, parse_csv(values["skills"]))
    brief.required_specializations = get_or_create_tags(
        Specialization, parse_csv(values["specializations"])
    )
    brief.preferred_tools = get_or_create_tags(Tool, parse_csv(values["tools"]))
    db.session.commit()
    flash("Brief published." if brief.status == "open" else "Brief saved as a draft.", "success")
    return redirect(url_for("brief_detail", brief_id=brief.id))


def record_event(engagement, event_type, note=""):
    db.session.add(
        EngagementEvent(
            engagement=engagement,
            actor_id=current_user().id,
            event_type=event_type,
            note=note,
        )
    )


@app.route("/")
def home():
    featured_creators = (
        CreatorProfile.query.join(User)
        .filter(User.is_active.is_(True))
        .order_by(CreatorProfile.created_at.desc())
        .limit(3)
        .all()
    )
    featured_briefs = (
        Brief.query.filter_by(status="open")
        .order_by(Brief.created_at.desc())
        .limit(3)
        .all()
    )
    return render_template(
        "index.html", featured_creators=featured_creators, featured_briefs=featured_briefs
    )


@app.route("/creators")
def creators():
    selected = {
        "q": request.args.get("q", "").strip(),
        "skills": request.args.getlist("skill"),
        "specializations": request.args.getlist("specialization"),
        "tools": request.args.getlist("tool"),
        "content_types": request.args.getlist("content_type"),
        "location": request.args.get("location", "").strip(),
        "availability": request.args.get("availability", "").strip(),
    }
    query = CreatorProfile.query.join(User).filter(User.is_active.is_(True))
    if selected["q"]:
        term = f"%{selected['q']}%"
        query = query.filter(
            or_(
                CreatorProfile.display_name.ilike(term),
                CreatorProfile.headline.ilike(term),
                CreatorProfile.bio.ilike(term),
                CreatorProfile.location.ilike(term),
                User.name.ilike(term),
                CreatorProfile.portfolio_items.any(
                    or_(
                        PortfolioItem.title.ilike(term),
                        PortfolioItem.description.ilike(term),
                        PortfolioItem.workflow_summary.ilike(term),
                        PortfolioItem.tool_tags.any(Tool.name.ilike(term)),
                    )
                ),
            )
        )
    if selected["skills"]:
        query = query.filter(
            or_(
                CreatorProfile.skill_tags.any(Skill.name.in_(selected["skills"])),
                CreatorProfile.portfolio_items.any(
                    PortfolioItem.skill_tags.any(Skill.name.in_(selected["skills"]))
                ),
            )
        )
    if selected["specializations"]:
        query = query.filter(
            or_(
                CreatorProfile.specializations.any(
                    Specialization.name.in_(selected["specializations"])
                ),
                CreatorProfile.portfolio_items.any(
                    PortfolioItem.specialization.in_(selected["specializations"])
                ),
            ),
        )
    if selected["tools"]:
        query = query.filter(
            or_(
                CreatorProfile.tool_tags.any(Tool.name.in_(selected["tools"])),
                CreatorProfile.portfolio_items.any(
                    PortfolioItem.tool_tags.any(Tool.name.in_(selected["tools"]))
                ),
            )
        )
    if selected["content_types"]:
        query = query.filter(
            or_(
                CreatorProfile.content_types.any(
                    ContentType.name.in_(selected["content_types"])
                ),
                CreatorProfile.portfolio_items.any(
                    db.func.lower(PortfolioItem.media_type).in_(
                        [value.lower() for value in selected["content_types"]]
                    )
                ),
            )
        )
    if selected["location"]:
        query = query.filter(CreatorProfile.location.ilike(f"%{selected['location']}%"))
    if selected["availability"]:
        query = query.filter(CreatorProfile.availability == selected["availability"])
    creator_profiles = query.order_by(CreatorProfile.display_name).all()
    return render_template(
        "creators.html",
        creators=creator_profiles,
        selected=selected,
        skills=Skill.query.order_by(Skill.name).all(),
        specializations=Specialization.query.order_by(Specialization.name).all(),
        tools=Tool.query.order_by(Tool.name).all(),
        content_types=ContentType.query.order_by(ContentType.name).all(),
    )


@app.route("/creators/<int:profile_id>")
def creator_profile(profile_id):
    profile = (
        CreatorProfile.query.join(User)
        .filter(User.is_active.is_(True), CreatorProfile.id == profile_id)
        .first_or_404()
    )
    return render_template("creator_profile.html", profile=profile)


@app.route("/profile/edit", methods=["GET", "POST"])
@role_required("creator")
def edit_profile():
    user = current_user()
    profile = creator_profile_for(user)
    if request.method == "POST":
        display_name = request.form.get("display_name", "").strip()
        if not display_name:
            flash("Display name is required.", "error")
            return render_template("profile_form.html", profile=profile), 400
        try:
            profile_url = optional_http_url(
                request.form.get("profile_url", "").strip(), "profile"
            )
        except ValueError as error:
            flash(str(error), "error")
            return render_template("profile_form.html", profile=profile), 400
        profile.display_name = display_name[:100]
        profile.headline = request.form.get("headline", "").strip()[:180]
        profile.bio = request.form.get("bio", "").strip()
        profile.category = request.form.get("category", "").strip()[:80] or "AI Content Creator"
        profile.location = request.form.get("location", "").strip()[:100]
        profile.availability = request.form.get("availability", "open")
        profile.profile_url = profile_url[:500]
        try:
            profile.starting_price = max(0, int(request.form.get("starting_price", "0")))
        except ValueError:
            flash("Starting price must be a whole number.", "error")
            return render_template("profile_form.html", profile=profile), 400
        profile.specializations = get_or_create_tags(
            Specialization, parse_csv(request.form.get("specializations"))
        )
        profile.content_types = get_or_create_tags(
            ContentType, parse_csv(request.form.get("content_types"))
        )
        profile.skill_tags = get_or_create_tags(Skill, parse_csv(request.form.get("skills")))
        profile.tool_tags = get_or_create_tags(Tool, parse_csv(request.form.get("tools")))
        profile.skills = ", ".join(tag.name for tag in profile.skill_tags)
        profile.tools = ", ".join(tag.name for tag in profile.tool_tags)
        db.session.commit()
        flash("Your creator profile has been updated.", "success")
        return redirect(url_for("creator_profile", profile_id=profile.id))
    return render_template("profile_form.html", profile=profile)


def owned_portfolio_item(item_id):
    item = db.session.get(PortfolioItem, item_id)
    if item is None:
        abort(404)
    if item.creator_profile.user_id != current_user().id:
        abort(403)
    return item


@app.route("/portfolio/new", methods=["GET", "POST"])
@role_required("creator")
def new_portfolio_item():
    profile = creator_profile_for(current_user())
    item = PortfolioItem()
    if request.method == "POST":
        return save_portfolio_item(item, profile)
    return render_template("portfolio_form.html", item=item)


@app.route("/portfolio/<int:item_id>")
def portfolio_detail(item_id):
    item = db.session.get(PortfolioItem, item_id)
    if item is None:
        abort(404)
    return render_template("portfolio_item.html", item=item)


@app.route("/portfolio/<int:item_id>/edit", methods=["GET", "POST"])
@role_required("creator")
def edit_portfolio_item(item_id):
    item = owned_portfolio_item(item_id)
    if request.method == "POST":
        return save_portfolio_item(item, item.creator_profile)
    return render_template("portfolio_form.html", item=item)


def save_portfolio_item(item, profile):
    title = request.form.get("title", "").strip()
    if not title:
        flash("Portfolio title is required.", "error")
        return render_template("portfolio_form.html", item=item), 400
    try:
        preview_url = optional_http_url(
            request.form.get("preview_url", "").strip(), "preview"
        )
        project_url = optional_http_url(
            request.form.get("project_url", "").strip(), "project"
        )
    except ValueError as error:
        flash(str(error), "error")
        return render_template("portfolio_form.html", item=item), 400
    year_value = request.form.get("year", "").strip()
    if year_value and (
        not year_value.isdigit() or not 1900 <= int(year_value) <= date.today().year + 1
    ):
        flash("Enter a valid portfolio year.", "error")
        return render_template("portfolio_form.html", item=item), 400
    item.title = title[:150]
    item.description = request.form.get("description", "").strip()
    item.media_type = request.form.get("media_type", "video").strip()
    item.specialization = request.form.get("specialization", "").strip()[:80]
    item.preview_url = preview_url[:500]
    item.image_url = item.preview_url
    item.project_url = project_url[:500]
    item.project_role = request.form.get("project_role", "").strip()[:180]
    item.workflow_summary = request.form.get("workflow_summary", "").strip()
    item.format = request.form.get("format", "").strip()[:80]
    item.aspect_ratio = request.form.get("aspect_ratio", "").strip()[:30]
    item.commercial_use = request.form.get("commercial_use", "Not specified").strip()[:150]
    item.year = int(year_value) if year_value else None
    item.skill_tags = get_or_create_tags(Skill, parse_csv(request.form.get("skills")))
    item.tool_tags = get_or_create_tags(Tool, parse_csv(request.form.get("tools")))
    item.creator_profile = profile
    db.session.add(item)
    db.session.commit()
    flash("Portfolio work saved.", "success")
    return redirect(url_for("portfolio_detail", item_id=item.id))


@app.route("/briefs")
def briefs():
    status = request.args.get("status", "open")
    query = Brief.query
    if status in {"open", "paused", "closed", "completed"}:
        query = query.filter_by(status=status)
    else:
        status = "open"
        query = query.filter_by(status=status)
    return render_template(
        "briefs.html",
        briefs=query.order_by(Brief.created_at.desc()).all(),
        status=status,
    )


@app.route("/briefs/<int:brief_id>")
def brief_detail(brief_id):
    brief = db.session.get(Brief, brief_id)
    if brief is None or (brief.status == "draft" and brief.brand_id != session.get("user_id")):
        abort(404)
    existing_application = None
    if session.get("user_role") == "creator":
        existing_application = Application.query.filter_by(
            brief_id=brief.id, creator_id=session["user_id"]
        ).first()
    return render_template(
        "brief_detail.html", brief=brief, existing_application=existing_application
    )


@app.route("/briefs/new", methods=["GET", "POST"])
@role_required("brand")
def new_brief():
    if request.method == "POST":
        return save_brief()
    return render_template(
        "brief_form.html",
        brief=None,
        values=brief_form_values(),
        errors=[],
        content_types=ContentType.query.order_by(ContentType.name).all(),
    )


@app.route("/briefs/<int:brief_id>/edit", methods=["GET", "POST"])
@role_required("brand")
def edit_brief(brief_id):
    brief = db.session.get(Brief, brief_id)
    if brief is None:
        abort(404)
    if brief.brand_id != current_user().id:
        abort(403)
    if brief.status not in {"draft", "open", "paused"}:
        flash("Closed or completed briefs can no longer be edited.", "error")
        return redirect(url_for("brief_detail", brief_id=brief.id))
    if request.method == "POST":
        return save_brief(brief)
    values = brief_form_values(brief)
    values["skills"] = ", ".join(skill.name for skill in brief.required_skills)
    values["specializations"] = ", ".join(
        specialization.name for specialization in brief.required_specializations
    )
    values["tools"] = ", ".join(tool.name for tool in brief.preferred_tools)
    return render_template(
        "brief_form.html",
        brief=brief,
        values=values,
        errors=[],
        content_types=ContentType.query.order_by(ContentType.name).all(),
    )


@app.route("/briefs/<int:brief_id>/status", methods=["POST"])
@role_required("brand")
def change_brief_status(brief_id):
    brief = db.session.get(Brief, brief_id)
    if brief is None:
        abort(404)
    if brief.brand_id != current_user().id:
        abort(403)
    new_status = request.form.get("status", "")
    if new_status not in {"open", "paused", "closed", "completed"}:
        abort(400)
    if brief.status == "completed":
        flash("A completed brief cannot be reopened or changed.", "error")
        return redirect(url_for("brief_detail", brief_id=brief.id))
    if new_status == "completed" and brief.status != "closed":
        flash("Close the brief before marking it completed.", "error")
        return redirect(url_for("brief_detail", brief_id=brief.id))
    brief.status = new_status
    db.session.commit()
    flash(f"Brief status updated to {new_status.replace('_', ' ')}.", "success")
    return redirect(url_for("brief_detail", brief_id=brief.id))


def suggest_brief(idea):
    cleaned = re.sub(r"\s+", " ", idea).strip()
    if not cleaned:
        return None
    lower = cleaned.lower()
    content_type = next(
        (name for name in ("animation", "video", "image", "graphics", "audio") if name in lower),
        "video",
    )
    title = cleaned.split(".")[0][:180].strip().capitalize()
    if len(title) > 75:
        title = title[:72].rsplit(" ", 1)[0] + "..."
    style = "Expressive, original, and aligned with the brand."
    if any(word in lower for word in ("playful", "fun", "bright")):
        style = "Playful, energetic, and visually bold."
    elif any(word in lower for word in ("premium", "luxury", "elegant")):
        style = "Premium, considered, and visually refined."
    elif any(word in lower for word in ("calm", "wellness", "mindful")):
        style = "Calm, warm, and human-centered."
    audience_match = re.search(r"\b(?:for|to reach|audience:)\s+([^,.!?;]{3,80})", cleaned, re.I)
    audience = audience_match.group(1).strip() if audience_match else "Customers interested in the brand and product."
    skills = "AI storytelling, Art direction"
    if content_type == "animation":
        skills = "AI animation, Motion design"
    elif content_type == "image":
        skills = "AI image generation, Art direction"
    return {
        "title": title or "Creative campaign",
        "goal": f"Create a memorable {content_type} campaign that supports: {cleaned}",
        "audience": audience,
        "description": cleaned,
        "requirements": "Confirm brand assets, review stages, and final delivery specifications with the selected creator.",
        "style": style,
        "content_type": content_type,
        "deliverables": f"One primary {content_type} concept and agreed final export.",
        "format": "Social-first digital content",
        "aspect_ratio": "9:16",
        "duration": "15-30 seconds",
        "category": content_type.title(),
        "budget": 25000,
        "quantity": 1,
        "timeline": "Agree schedule with creator",
        "deadline": "",
        "commercial_use": "organic_only",
        "usage_duration": "30 days",
        "territory": "India",
        "exclusivity": "none",
        "allow_edits": False,
        "skills": skills,
        "specializations": "AI Filmmaking" if content_type == "video" else "Generative Content",
        "tools": "",
        "status": "draft",
    }


@app.route("/briefs/builder", methods=["GET", "POST"])
@role_required("brand")
def brief_builder():
    if request.method == "POST":
        if request.form.get("save") == "yes":
            return save_brief()
        idea = request.form.get("idea", "").strip()
        if not idea:
            flash("Describe your rough campaign idea first.", "error")
            return render_template("brief_builder.html", idea=idea), 400
        suggestion = suggest_brief(idea)
        flash("Suggested draft created locally from your idea. Review and edit every field.", "success")
        return render_template("brief_builder.html", idea=idea, values=suggestion)
    return render_template("brief_builder.html", idea="", values=None)


@app.route("/briefs/<int:brief_id>/apply", methods=["POST"])
@role_required("creator")
def apply_to_brief(brief_id):
    brief = db.session.get(Brief, brief_id)
    if brief is None:
        abort(404)
    if brief.status != "open":
        flash("This brief is not accepting applications.", "error")
        return redirect(url_for("brief_detail", brief_id=brief.id))
    existing = Application.query.filter_by(
        brief_id=brief.id, creator_id=current_user().id
    ).first()
    if existing:
        flash("You have already applied to this brief.", "error")
    else:
        application = Application(
            brief=brief,
            creator=current_user(),
            message=request.form.get("message", "").strip()[:5000],
            status="applied",
        )
        db.session.add(application)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("You have already applied to this brief.", "error")
            return redirect(url_for("brief_detail", brief_id=brief.id))
        flash("Your application has been sent.", "success")
    return redirect(url_for("brief_detail", brief_id=brief.id))


@app.route("/briefs/<int:brief_id>/applications")
@role_required("brand")
def brief_applications(brief_id):
    brief = db.session.get(Brief, brief_id)
    if brief is None:
        abort(404)
    if brief.brand_id != current_user().id:
        abort(403)
    return render_template(
        "applications.html",
        brief=brief,
        applications=Application.query.filter_by(brief_id=brief.id)
        .order_by(Application.created_at.desc())
        .all(),
    )


@app.route("/applications/<int:application_id>/status", methods=["POST"])
@role_required("brand")
def update_application(application_id):
    application = db.session.get(Application, application_id)
    if application is None:
        abort(404)
    if application.brief.brand_id != current_user().id:
        abort(403)
    if application.status in {"accepted", "declined"}:
        flash("This application is no longer accepting status changes.", "error")
        return redirect(url_for("brief_applications", brief_id=application.brief_id))
    new_status = request.form.get("status", "")
    if new_status not in {"shortlisted", "accepted", "declined"}:
        abort(400)
    if new_status == "accepted":
        other_acceptance = Application.query.filter(
            Application.brief_id == application.brief_id,
            Application.status == "accepted",
            Application.id != application.id,
        ).first()
        if other_acceptance:
            flash("This brief already has an accepted creator.", "error")
            return redirect(url_for("brief_applications", brief_id=application.brief_id))
        application.status = "accepted"
        engagement = application.engagement or Engagement(application=application, status="accepted")
        db.session.add(engagement)
        db.session.flush()
        record_event(engagement, "accepted", "Brand accepted the creator application.")
    else:
        application.status = new_status
    db.session.commit()
    flash(f"Application {new_status}.", "success")
    return redirect(url_for("brief_applications", brief_id=application.brief_id))


def get_participant_engagement(engagement_id):
    engagement = db.session.get(Engagement, engagement_id)
    if engagement is None:
        abort(404)
    application = engagement.application
    if current_user().id not in {application.creator_id, application.brief.brand_id}:
        abort(403)
    return engagement


@app.route("/engagements/<int:engagement_id>")
@login_required
def engagement_detail(engagement_id):
    engagement = get_participant_engagement(engagement_id)
    return render_template("engagement_detail.html", engagement=engagement)


@app.route("/engagements/<int:engagement_id>/start", methods=["POST"])
@role_required("creator")
def start_engagement(engagement_id):
    engagement = get_participant_engagement(engagement_id)
    if engagement.application.creator_id != current_user().id:
        abort(403)
    if engagement.status != "accepted":
        flash("Only an accepted engagement can be started.", "error")
        return redirect(url_for("engagement_detail", engagement_id=engagement.id))
    engagement.status = "in_progress"
    record_event(engagement, "in_progress", "Creator started work on the engagement.")
    db.session.commit()
    flash("Engagement started.", "success")
    return redirect(url_for("engagement_detail", engagement_id=engagement.id))


@app.route("/engagements/<int:engagement_id>/deliveries", methods=["POST"])
@role_required("creator")
def submit_delivery(engagement_id):
    engagement = get_participant_engagement(engagement_id)
    if engagement.application.creator_id != current_user().id:
        abort(403)
    if engagement.status not in {"accepted", "in_progress", "revision_requested"}:
        flash("This engagement is not accepting a delivery right now.", "error")
        return redirect(url_for("engagement_detail", engagement_id=engagement.id))
    link = request.form.get("link", "").strip()
    if not link or urlsplit(link).scheme not in {"http", "https"} or not urlsplit(link).netloc:
        flash("Enter a complete delivery link starting with https://.", "error")
        return redirect(url_for("engagement_detail", engagement_id=engagement.id))
    latest = engagement.deliveries[-1] if engagement.deliveries else None
    revision_number = (latest.revision_number + 1) if latest else 0
    delivery = Delivery(
        engagement=engagement,
        submitted_by=current_user(),
        link=link[:1000],
        note=request.form.get("note", "").strip()[:5000],
        revision_number=revision_number,
        status="submitted",
    )
    engagement.status = "submitted"
    db.session.add(delivery)
    record_event(engagement, "delivery_submitted", delivery.note)
    db.session.commit()
    flash("Delivery submitted for brand review.", "success")
    return redirect(url_for("engagement_detail", engagement_id=engagement.id))


@app.route("/engagements/<int:engagement_id>/review", methods=["POST"])
@role_required("brand")
def review_delivery(engagement_id):
    engagement = get_participant_engagement(engagement_id)
    if engagement.application.brief.brand_id != current_user().id:
        abort(403)
    latest = engagement.deliveries[-1] if engagement.deliveries else None
    if latest is None or engagement.status != "submitted":
        flash("There is no submitted delivery to review.", "error")
        return redirect(url_for("engagement_detail", engagement_id=engagement.id))
    action = request.form.get("action")
    if action == "revise":
        feedback = request.form.get("feedback", "").strip()
        if not feedback:
            flash("Add feedback to explain the requested revision.", "error")
            return redirect(url_for("engagement_detail", engagement_id=engagement.id))
        latest.feedback = feedback[:5000]
        latest.status = "revision_requested"
        engagement.status = "revision_requested"
        record_event(engagement, "revision_requested", feedback)
        message = "Revision requested."
    elif action == "approve":
        latest.status = "approved"
        engagement.status = "approved"
        record_event(engagement, "delivery_approved", "Brand approved the latest delivery.")
        message = "Delivery approved."
    else:
        abort(400)
    db.session.commit()
    flash(message, "success")
    return redirect(url_for("engagement_detail", engagement_id=engagement.id))


@app.route("/engagements/<int:engagement_id>/complete", methods=["POST"])
@role_required("brand")
def complete_engagement(engagement_id):
    engagement = get_participant_engagement(engagement_id)
    if engagement.application.brief.brand_id != current_user().id:
        abort(403)
    if engagement.status != "approved":
        flash("Approve the latest delivery before completing this engagement.", "error")
        return redirect(url_for("engagement_detail", engagement_id=engagement.id))
    engagement.status = "completed"
    record_event(engagement, "completed", "Brand marked the engagement complete.")
    db.session.commit()
    flash("Engagement completed.", "success")
    return redirect(url_for("engagement_detail", engagement_id=engagement.id))


@app.route("/applications")
@role_required("creator")
def my_applications():
    applications = Application.query.filter_by(creator_id=current_user().id).order_by(
        Application.created_at.desc()
    ).all()
    return render_template("applications.html", applications=applications, brief=None)


@app.route("/dashboard")
@login_required
def dashboard():
    user = current_user()
    if user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    if user.role == "brand":
        briefs_owned = Brief.query.filter_by(brand_id=user.id).order_by(
            Brief.created_at.desc()
        ).all()
        engagements = (
            Engagement.query.join(Application)
            .join(Brief)
            .filter(Brief.brand_id == user.id)
            .order_by(Engagement.updated_at.desc())
            .all()
        )
        return render_template(
            "dashboard.html",
            user=user,
            briefs=briefs_owned,
            engagements=engagements,
            applications=[],
        )
    profile = creator_profile_for(user)
    applications = Application.query.filter_by(creator_id=user.id).order_by(
        Application.created_at.desc()
    ).all()
    open_briefs = Brief.query.filter_by(status="open").order_by(Brief.created_at.desc()).limit(5).all()
    return render_template(
        "dashboard.html",
        user=user,
        profile=profile,
        applications=applications,
        open_briefs=open_briefs,
        engagements=[],
        briefs=[],
    )


@app.route("/admin")
@role_required("admin")
def admin_dashboard():
    search = request.args.get("q", "").strip()[:120]
    role = request.args.get("role", "").strip().lower()
    page_number = max(1, request.args.get("page", 1, type=int))
    users_query = User.query
    if search:
        term = f"%{search}%"
        users_query = users_query.filter(
            or_(User.name.ilike(term), User.email.ilike(term))
        )
    if role in {"creator", "brand", "admin"}:
        users_query = users_query.filter_by(role=role)
    else:
        role = ""
    users = users_query.order_by(User.created_at.desc(), User.id.desc()).paginate(
        page=page_number,
        per_page=25,
        error_out=False,
    )
    stats = {
        "users": User.query.count(),
        "active_users": User.query.filter_by(is_active=True).count(),
        "creators": User.query.filter_by(role="creator").count(),
        "brands": User.query.filter_by(role="brand").count(),
        "open_briefs": Brief.query.filter_by(status="open").count(),
        "applications": Application.query.count(),
    }
    return render_template(
        "admin.html",
        stats=stats,
        users=users,
        search=search,
        role_filter=role,
    )


def email_verification_ready():
    public_url = app.config["PUBLIC_BASE_URL"]
    parsed_url = urlsplit(public_url)
    return bool(
        app.config["SMTP_HOST"]
        and app.config["MAIL_FROM"]
        and parsed_url.scheme in {"http", "https"}
        and parsed_url.netloc
        and not parsed_url.username
        and not parsed_url.password
        and app.config["SMTP_USE_SSL"] != app.config["SMTP_USE_TLS"]
        and bool(app.config["SMTP_USERNAME"]) == bool(app.config["SMTP_PASSWORD"])
    )


def gmail_app_password_ready():
    if app.config["SMTP_HOST"].lower() not in {
        "smtp.gmail.com",
        "smtp.googlemail.com",
    }:
        return True
    password = "".join(app.config["SMTP_PASSWORD"].split())
    return len(password) == 16


def email_verification_token(user):
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    return serializer.dumps(
        {"user_id": user.id, "email": user.email},
        salt="creatora-email-verification",
    )


def password_reset_token(user):
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    return serializer.dumps(
        {
            "user_id": user.id,
            "email": user.email,
            "updated_at": user.updated_at.isoformat(),
        },
        salt="creatora-password-reset",
    )


def load_password_reset_token(token):
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    return serializer.loads(
        token,
        salt="creatora-password-reset",
        max_age=app.config["PASSWORD_RESET_MAX_AGE"],
    )


def send_email_message(message):
    smtp_class = smtplib.SMTP_SSL if app.config["SMTP_USE_SSL"] else smtplib.SMTP
    smtp_options = {"timeout": 10}
    if app.config["SMTP_USE_SSL"]:
        smtp_options["context"] = ssl.create_default_context()
    with smtp_class(
        app.config["SMTP_HOST"],
        app.config["SMTP_PORT"],
        **smtp_options,
    ) as smtp:
        if app.config["SMTP_USE_TLS"]:
            smtp.starttls(context=ssl.create_default_context())
        if app.config["SMTP_USERNAME"]:
            smtp_password = app.config["SMTP_PASSWORD"]
            if app.config["SMTP_HOST"].lower() in {
                "smtp.gmail.com",
                "smtp.googlemail.com",
            }:
                smtp_password = "".join(smtp_password.split())
            smtp.login(
                app.config["SMTP_USERNAME"],
                smtp_password,
            )
        smtp.send_message(message)


def send_verification_email(user):
    token = email_verification_token(user)
    expiry_hours = max(
        1,
        (app.config["EMAIL_VERIFICATION_MAX_AGE"] + 3599) // 3600,
    )
    verification_url = (
        f"{app.config['PUBLIC_BASE_URL']}"
        f"/verify-email/{token}"
    )
    message = EmailMessage()
    message["Subject"] = "Verify your Creatora AI email"
    message["From"] = app.config["MAIL_FROM"]
    message["To"] = user.email
    message.set_content(
        "Welcome to Creatora AI.\n\n"
        "Confirm your email by opening this link and submitting the confirmation form:\n"
        f"{verification_url}\n\n"
        f"This link expires in {expiry_hours} hours. If you did not create this account, "
        "you can ignore this message."
    )

    send_email_message(message)


def send_password_reset_email(user):
    token = password_reset_token(user)
    expiry_minutes = max(
        1,
        (app.config["PASSWORD_RESET_MAX_AGE"] + 59) // 60,
    )
    reset_url = f"{app.config['PUBLIC_BASE_URL']}/reset-password/{token}"
    message = EmailMessage()
    message["Subject"] = "Reset your Creatora AI password"
    message["From"] = app.config["MAIL_FROM"]
    message["To"] = user.email
    message.set_content(
        "A password reset was requested for your Creatora AI account.\n\n"
        "Choose a new password using this link:\n"
        f"{reset_url}\n\n"
        f"This link expires in {expiry_minutes} minutes and can be used only once. "
        "If you did not request a reset, you can ignore this email."
    )
    send_email_message(message)


def load_email_verification_token(token):
    serializer = URLSafeTimedSerializer(app.config["SECRET_KEY"])
    return serializer.loads(
        token,
        salt="creatora-email-verification",
        max_age=app.config["EMAIL_VERIFICATION_MAX_AGE"],
    )


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if app.config["SUPABASE_AUTH_ENABLED"]:
            try:
                options = {}
                if app.config["PUBLIC_BASE_URL"]:
                    options["redirect_to"] = (
                        f"{app.config['PUBLIC_BASE_URL']}/reset-password"
                    )
                supabase_client().auth.reset_password_for_email(email, options)
            except (AuthError, httpx.HTTPError) as error:
                app.logger.warning(
                    "Supabase password reset request failed (%s, code=%s, status=%s).",
                    type(error).__name__,
                    getattr(error, "code", None),
                    getattr(error, "status", None),
                )
                flash(
                    "Password reset is temporarily unavailable. Please try again later.",
                    "error",
                )
                return render_template("forgot_password.html"), 503
        else:
            if not email_verification_ready():
                flash(
                    "Password reset email is not configured. Set SMTP_HOST, MAIL_FROM, "
                    "and PUBLIC_BASE_URL in .env, then try again.",
                    "error",
                )
                return render_template("forgot_password.html"), 503
            if not gmail_app_password_ready():
                flash(
                    "Gmail SMTP requires a 16-character Google App Password in "
                    "SMTP_PASSWORD. Update .env and restart the app.",
                    "error",
                )
                return render_template("forgot_password.html"), 503
            user = User.query.filter_by(email=email).first() if email else None
            if user is not None and user.is_active and user.password_hash:
                try:
                    send_password_reset_email(user)
                except (OSError, smtplib.SMTPException, ValueError) as error:
                    app.logger.error(
                        "Password reset email delivery failed (%s).",
                        type(error).__name__,
                    )
                    flash(
                        "Password reset email could not be sent right now. Please try again later.",
                        "error",
                    )
                    return render_template("forgot_password.html"), 503

        flash(
            "If an active account uses that email, password reset instructions have been sent.",
            "success",
        )
        return redirect(url_for("login"))
    return render_template("forgot_password.html")


@app.route("/reset-password", defaults={"token": None}, methods=["GET", "POST"])
@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    if token is None:
        if not app.config["SUPABASE_AUTH_ENABLED"]:
            abort(404)
        if request.method == "GET":
            return render_template("reset_password.html", supabase_recovery=True)

        access_token = request.form.get("access_token", "").strip()
        refresh_token = request.form.get("refresh_token", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("reset_password.html", supabase_recovery=True), 400
        if password != confirm_password:
            flash("The passwords do not match.", "error")
            return render_template("reset_password.html", supabase_recovery=True), 400
        if not access_token or not refresh_token:
            flash("The recovery link is invalid or expired. Request a new one.", "error")
            return render_template("reset_password.html", supabase_recovery=True), 400
        try:
            auth = supabase_client().auth
            auth.set_session(access_token, refresh_token)
            auth.update_user({"password": password})
        except (AuthError, httpx.HTTPError, ValueError, IndexError) as error:
            app.logger.warning(
                "Supabase password reset completion failed (%s, code=%s, status=%s).",
                type(error).__name__,
                getattr(error, "code", None),
                getattr(error, "status", None),
            )
            flash("The recovery link is invalid or expired. Request a new one.", "error")
            return render_template("reset_password.html", supabase_recovery=True), 400
        flash("Your password has been reset. You can now log in.", "success")
        return redirect(url_for("login"))

    try:
        payload = load_password_reset_token(token)
    except (SignatureExpired, BadSignature):
        flash("That password reset link is invalid or expired. Request a new one.", "error")
        return redirect(url_for("forgot_password"))
    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("user_id"), int)
        or not isinstance(payload.get("email"), str)
        or not isinstance(payload.get("updated_at"), str)
    ):
        flash("That password reset link is invalid. Request a new one.", "error")
        return redirect(url_for("forgot_password"))
    user = db.session.get(User, payload["user_id"])
    if (
        user is None
        or user.email != payload["email"]
        or user.updated_at.isoformat() != payload["updated_at"]
        or not user.is_active
        or user.auth_user_id
    ):
        flash("That password reset link is invalid or expired. Request a new one.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("reset_password.html", supabase_recovery=False), 400
        if password != confirm_password:
            flash("The passwords do not match.", "error")
            return render_template("reset_password.html", supabase_recovery=False), 400
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        flash("Your password has been reset. You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html", supabase_recovery=False)


@app.after_request
def prevent_password_reset_caching(response):
    if request.endpoint == "reset_password":
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response


@app.route("/login", methods=["GET", "POST"])
def login():
    login_template = "login.html"
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if app.config["SUPABASE_AUTH_ENABLED"]:
            try:
                auth_response = supabase_client().auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
            except (AuthError, httpx.HTTPError) as error:
                app.logger.warning(
                    "Supabase sign-in failed (%s, code=%s, status=%s).",
                    type(error).__name__,
                    getattr(error, "code", None),
                    getattr(error, "status", None),
                )
                if getattr(error, "code", None) == "email_not_confirmed":
                    flash(
                        "Please confirm your email using the latest Supabase confirmation email, then try signing in again.",
                        "error",
                    )
                else:
                    flash(
                        "Invalid email or password, or sign-in is temporarily unavailable.",
                        "error",
                    )
                return render_template(login_template), 401
            auth_user = _auth_value(auth_response, "user")
            if auth_user is None:
                flash("Supabase did not return an authenticated account.", "error")
                return render_template(login_template), 401
            try:
                user = marketplace_user_for_auth(auth_user)
            except MarketplaceIdentityError as error:
                db.session.rollback()
                flash(str(error), "error")
                return render_template(login_template), 403
            except IntegrityError:
                db.session.rollback()
                app.logger.exception("Could not link authenticated Supabase user.")
                flash("Your account could not be linked to Creatora. Please try again.", "error")
                return render_template(login_template), 503
        else:
            user = User.query.filter_by(email=email).first() if email else None
            if (
                not user
                or not user.password_hash
                or not check_password_hash(user.password_hash, password)
            ):
                flash("Invalid email or password.", "error")
                return render_template(login_template), 401
        if not app.config["SUPABASE_AUTH_ENABLED"] and not user.email_verified:
            flash(
                "Please verify your email before logging in. "
                "You can request another verification email below.",
                "error",
            )
            return render_template(login_template), 403
        if not user.is_active:
            flash("This account is inactive. Please contact support.", "error")
            return render_template(login_template), 403
        session.clear()
        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_role"] = user.role
        next_url = request.args.get("next", "")
        default_endpoint = "admin_dashboard" if user.role == "admin" else "dashboard"
        return redirect(
            next_url if safe_next_url(next_url) else url_for(default_endpoint)
        )
    return render_template(login_template)


@app.route("/admin/login")
def admin_login():
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if user is not None and user.is_active and user.role == "admin":
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "creator").strip().lower()
        if not name or not email or not password:
            flash("Please fill in all fields.", "error")
            return render_template("register.html"), 400
        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("register.html"), 400
        if role not in ("creator", "brand"):
            flash("Invalid account type.", "error")
            return render_template("register.html"), 400
        if app.config["SUPABASE_AUTH_ENABLED"]:
            try:
                auth_response = supabase_client().auth.sign_up(
                    {
                        "email": email,
                        "password": password,
                        "options": {"data": {"name": name, "role": role}},
                    }
                )
            except (AuthError, httpx.HTTPError) as error:
                app.logger.warning(
                    "Supabase sign-up failed (%s, code=%s, status=%s).",
                    type(error).__name__,
                    getattr(error, "code", None),
                    getattr(error, "status", None),
                )
                message = (
                    supabase_signup_error_message(error, email, password)
                    if isinstance(error, AuthError)
                    else "Could not reach Supabase Auth. Check your internet connection and Supabase project URL, then try again."
                )
                flash(message, "error")
                return render_template("register.html"), 400
            auth_user = _auth_value(auth_response, "user")
            auth_session = _auth_value(auth_response, "session")
            if auth_user is None:
                flash(
                    "Supabase did not return an account. Check your Supabase email sign-up settings.",
                    "error",
                )
                return render_template("register.html"), 502
            identities = _auth_value(auth_user, "identities")
            if auth_session is None and identities == []:
                flash("An account with that email may already exist. Try logging in.", "error")
                return render_template("register.html"), 409
            try:
                user = marketplace_user_for_auth(
                    auth_user,
                    role_if_new=role,
                    name_if_new=name,
                    activate=auth_session is not None,
                )
            except MarketplaceIdentityError as error:
                db.session.rollback()
                flash(str(error), "error")
                return render_template("register.html"), 409
            except IntegrityError:
                db.session.rollback()
                app.logger.exception("Could not save newly registered Supabase user.")
                flash(
                    "Supabase created the sign-in, but Creatora could not save the profile. Please try logging in.",
                    "error",
                )
                return render_template("register.html"), 503
            if auth_session is None:
                flash(
                    "Account created. Check your email to confirm it, then log in.",
                    "success",
                )
                return redirect(url_for("login"))
            session.clear()
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["user_role"] = user.role
            flash("Your account is ready.", "success")
            return redirect(url_for("dashboard"))

        verification_required = app.config["EMAIL_VERIFICATION_REQUIRED"]
        if verification_required and not email_verification_ready():
            flash(
                "Email verification is enabled, but email delivery is not configured. "
                "Set SMTP_HOST, MAIL_FROM, and PUBLIC_BASE_URL in .env, then try again.",
                "error",
            )
            return render_template("register.html"), 503

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
            is_active=True,
            email_verified=not verification_required,
        )
        if role == "creator":
            user.creator_profile = CreatorProfile(display_name=name)
        db.session.add(user)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("This email is already registered. Please log in.", "error")
            return render_template("register.html"), 409
        if verification_required:
            try:
                send_verification_email(user)
            except (OSError, smtplib.SMTPException, ValueError) as error:
                app.logger.error(
                    "Verification email delivery failed (%s).",
                    type(error).__name__,
                )
                flash(
                    "Your account was created but the verification email could not "
                    "be sent. Use the resend form on the login page.",
                    "error",
                )
                return render_template("register.html"), 503
            flash(
                "Account created. Check your email for a verification link before logging in.",
                "success",
            )
            return redirect(url_for("login"))

        session.clear()
        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_role"] = user.role
        flash("Your account is ready.", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/verify-email/<token>", methods=["GET", "POST"])
def verify_email(token):
    try:
        payload = load_email_verification_token(token)
    except SignatureExpired:
        flash("That verification link has expired. Request a new one below.", "error")
        return redirect(url_for("resend_verification"))
    except BadSignature:
        flash("That verification link is invalid. Request a new one below.", "error")
        return redirect(url_for("resend_verification"))

    if (
        not isinstance(payload, dict)
        or not isinstance(payload.get("user_id"), int)
        or not isinstance(payload.get("email"), str)
    ):
        flash("That verification link is invalid. Request a new one below.", "error")
        return redirect(url_for("resend_verification"))

    user = db.session.get(User, payload["user_id"])
    if user is None or user.email != payload["email"]:
        flash("That verification link is invalid. Request a new one below.", "error")
        return redirect(url_for("resend_verification"))
    if user.email_verified:
        flash("Your email is already verified. You can log in.", "success")
        return redirect(url_for("login"))

    if request.method == "POST":
        user.email_verified = True
        db.session.commit()
        flash("Your email is verified. You can now log in.", "success")
        return redirect(url_for("login"))

    expiry_hours = max(
        1,
        (app.config["EMAIL_VERIFICATION_MAX_AGE"] + 3599) // 3600,
    )
    return render_template(
        "verify_email.html",
        token=token,
        expiry_hours=expiry_hours,
    )


@app.route("/resend-verification", methods=["GET", "POST"])
def resend_verification():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if (
            app.config["EMAIL_VERIFICATION_REQUIRED"]
            and not app.config["SUPABASE_AUTH_ENABLED"]
            and not email_verification_ready()
        ):
            flash(
                "Email verification is enabled, but email delivery is not configured. "
                "Set SMTP_HOST, MAIL_FROM, and PUBLIC_BASE_URL in .env.",
                "error",
            )
            return render_template("resend_verification.html"), 503

        if app.config["SUPABASE_AUTH_ENABLED"] and email:
            try:
                supabase_client().auth.resend({"type": "signup", "email": email})
            except (AuthError, httpx.HTTPError) as error:
                app.logger.error(
                    "Supabase verification email resend failed (%s, code=%s, status=%s).",
                    type(error).__name__,
                    getattr(error, "code", None),
                    getattr(error, "status", None),
                )
                flash(
                    "If the address belongs to an unverified account, a new email may be sent. "
                    "Please try again later if it does not arrive.",
                    "success",
                )
                return redirect(url_for("login"))
        elif app.config["EMAIL_VERIFICATION_REQUIRED"]:
            user = User.query.filter_by(email=email).first() if email else None
            if (
                user is not None
                and not user.email_verified
                and not user.auth_user_id
            ):
                try:
                    send_verification_email(user)
                except (OSError, smtplib.SMTPException, ValueError) as error:
                    app.logger.error(
                        "Verification email resend failed (%s).",
                        type(error).__name__,
                    )
                    flash(
                        "We could not send a verification email right now. Please try again later.",
                        "error",
                    )
                    return render_template("resend_verification.html"), 503

        flash(
            "If an unverified account exists for that address, a verification email has been sent.",
            "success",
        )
        return redirect(url_for("login"))

    return render_template("resend_verification.html")


@app.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


@app.route("/health")
def health():
    return {"status": "ok", "application": "Creatora AI"}


@app.errorhandler(403)
def forbidden(_error):
    return render_template("errors/403.html"), 403


@app.errorhandler(404)
def not_found(_error):
    return render_template("errors/404.html"), 404


@app.errorhandler(CSRFError)
def csrf_error(_error):
    return render_template("errors/400.html"), 400


@app.cli.command("init-db")
def init_db_command():
    """Create missing tables and add new columns without dropping data."""
    initialize_database()
    click.echo("Database schema initialized successfully.")


@app.cli.command("promote-admin")
@click.argument("email")
def promote_admin_command(email):
    """Grant admin access to an existing active, verified account."""
    user = User.query.filter(db.func.lower(User.email) == email.strip().lower()).first()
    if user is None:
        raise click.ClickException("No account exists with that email address.")
    if not user.is_active or not user.email_verified:
        raise click.ClickException(
            "Only active accounts with verified email addresses can become admins."
        )
    user.role = "admin"
    db.session.commit()
    click.echo("Admin access granted.")


@app.cli.command("create-admin")
def create_admin_command():
    """Create a local admin account using securely prompted credentials."""
    if app.config["SUPABASE_AUTH_ENABLED"]:
        raise click.ClickException(
            "Supabase Auth is enabled. Register the account through the app, "
            "confirm its email, then run 'flask --app app promote-admin EMAIL'."
        )
    name = click.prompt("Admin name").strip()
    email = click.prompt("Admin email").strip().lower()
    if not name or not email or "@" not in email or any(char.isspace() for char in email):
        raise click.ClickException("Enter a name and a valid email address.")
    password = click.prompt(
        "Admin password",
        hide_input=True,
        confirmation_prompt=True,
    )
    if len(password) < 8:
        raise click.ClickException("Password must be at least 8 characters.")
    if User.query.filter_by(email=email).first() is not None:
        raise click.ClickException(
            "An account with that email already exists. Use 'promote-admin' instead."
        )
    user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role="admin",
        is_active=True,
        email_verified=True,
    )
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise click.ClickException(
            "An account with that email already exists. Use 'promote-admin' instead."
        ) from None
    click.echo("Admin account created. Sign in at /admin/login.")


register_seed_command(app)


if os.getenv("SKIP_DB_INIT", "0") != "1":
    with app.app_context():
        try:
            initialize_database()
            print("[startup] Database initialized successfully.")
        except Exception as _db_init_err:
            db.session.rollback()
            print(
                f"[startup] WARNING: Could not initialize database: "
                f"{type(_db_init_err).__name__}: {_db_init_err}"
            )


if __name__ == "__main__":
    app.run(debug=True)
 
