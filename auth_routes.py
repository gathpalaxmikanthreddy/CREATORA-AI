import secrets
from functools import wraps
from urllib.parse import urlsplit

import httpx
from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy.exc import IntegrityError
from supabase import create_client
from supabase_auth.errors import AuthError
from werkzeug.security import check_password_hash, generate_password_hash

from models import CreatorProfile, User, db


auth_bp = Blueprint("auth", __name__)


class MarketplaceIdentityError(Exception):
    """Raised when a Supabase identity cannot be safely mapped to a local user."""


def supabase_client():
    if not current_app.config["SUPABASE_AUTH_ENABLED"]:
        raise RuntimeError("Supabase Auth is not configured.")
    return create_client(
        current_app.config["SUPABASE_URL"], current_app.config["SUPABASE_KEY"]
    )


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

    if activate:
        user.is_active = True
    if user.role == "creator" and user.creator_profile is None:
        user.creator_profile = CreatorProfile(display_name=user.name)
    db.session.commit()
    return user


def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        user_id = session.get("user_id")
        user = db.session.get(User, user_id) if user_id else None
        if user is None or not user.is_active:
            session.clear()
            flash("Please log in to continue.", "error")
            return redirect(url_for("auth.login", next=request.path))
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


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if current_app.config["SUPABASE_AUTH_ENABLED"]:
            try:
                auth_response = supabase_client().auth.sign_in_with_password(
                    {"email": email, "password": password}
                )
            except (AuthError, httpx.HTTPError) as error:
                current_app.logger.warning(
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
                return render_template("login.html"), 401
            auth_user = _auth_value(auth_response, "user")
            if auth_user is None:
                flash("Supabase did not return an authenticated account.", "error")
                return render_template("login.html"), 401
            try:
                user = marketplace_user_for_auth(auth_user)
            except MarketplaceIdentityError as error:
                db.session.rollback()
                flash(str(error), "error")
                return render_template("login.html"), 403
            except IntegrityError:
                db.session.rollback()
                current_app.logger.exception(
                    "Could not link authenticated Supabase user."
                )
                flash(
                    "Your account could not be linked to Creatora. Please try again.",
                    "error",
                )
                return render_template("login.html"), 503
        else:
            user = User.query.filter_by(email=email).first() if email else None
            if (
                not user
                or not user.password_hash
                or not check_password_hash(user.password_hash, password)
            ):
                flash("Invalid email or password.", "error")
                return render_template("login.html"), 401
        if not user.is_active:
            flash("This account is inactive. Please contact support.", "error")
            return render_template("login.html"), 403
        session.clear()
        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_role"] = user.role
        next_url = request.args.get("next", "")
        return redirect(
            next_url if safe_next_url(next_url) else url_for("dashboard")
        )
    return render_template("login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
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

        if current_app.config["SUPABASE_AUTH_ENABLED"]:
            try:
                auth_response = supabase_client().auth.sign_up(
                    {
                        "email": email,
                        "password": password,
                        "options": {"data": {"name": name, "role": role}},
                    }
                )
            except (AuthError, httpx.HTTPError) as error:
                current_app.logger.warning(
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
                flash(
                    "An account with that email may already exist. Try logging in instead.",
                    "error",
                )
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
                current_app.logger.exception(
                    "Could not save newly registered Supabase user."
                )
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
                return redirect(url_for("auth.login"))
            session.clear()
            session["user_id"] = user.id
            session["user_name"] = user.name
            session["user_role"] = user.role
            flash("Your account is ready.", "success")
            return redirect(url_for("dashboard"))

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
            role=role,
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
        session.clear()
        session["user_id"] = user.id
        session["user_name"] = user.name
        session["user_role"] = user.role
        flash("Your account is ready.", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))
