from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, Identity, UniqueConstraint

db = SQLAlchemy()


def utc_now():
    return datetime.now(timezone.utc)


profile_specializations = db.Table(
    "profile_specializations",
    db.Column("profile_id", db.Integer, db.ForeignKey("creator_profiles.id"), primary_key=True),
    db.Column("specialization_id", db.Integer, db.ForeignKey("specializations.id"), primary_key=True),
)

profile_content_types = db.Table(
    "profile_content_types",
    db.Column("profile_id", db.Integer, db.ForeignKey("creator_profiles.id"), primary_key=True),
    db.Column("content_type_id", db.Integer, db.ForeignKey("content_types.id"), primary_key=True),
)

profile_skills = db.Table(
    "profile_skills",
    db.Column("profile_id", db.Integer, db.ForeignKey("creator_profiles.id"), primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skills.id"), primary_key=True),
)

profile_tools = db.Table(
    "profile_tools",
    db.Column("profile_id", db.Integer, db.ForeignKey("creator_profiles.id"), primary_key=True),
    db.Column("tool_id", db.Integer, db.ForeignKey("tools.id"), primary_key=True),
)

portfolio_skills = db.Table(
    "portfolio_skills",
    db.Column("portfolio_item_id", db.Integer, db.ForeignKey("portfolio_items.id"), primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skills.id"), primary_key=True),
)

portfolio_tools = db.Table(
    "portfolio_tools",
    db.Column("portfolio_item_id", db.Integer, db.ForeignKey("portfolio_items.id"), primary_key=True),
    db.Column("tool_id", db.Integer, db.ForeignKey("tools.id"), primary_key=True),
)

brief_skills = db.Table(
    "brief_skills",
    db.Column("brief_id", db.Integer, db.ForeignKey("briefs.id"), primary_key=True),
    db.Column("skill_id", db.Integer, db.ForeignKey("skills.id"), primary_key=True),
)

brief_tools = db.Table(
    "brief_tools",
    db.Column("brief_id", db.Integer, db.ForeignKey("briefs.id"), primary_key=True),
    db.Column("tool_id", db.Integer, db.ForeignKey("tools.id"), primary_key=True),
)

brief_specializations = db.Table(
    "brief_specializations",
    db.Column("brief_id", db.Integer, db.ForeignKey("briefs.id"), primary_key=True),
    db.Column("specialization_id", db.Integer, db.ForeignKey("specializations.id"), primary_key=True),
)


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('creator', 'brand', 'admin')", name="ck_user_role"),)

    id = db.Column(db.Integer, Identity(), primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    auth_user_id = db.Column(db.String(36), unique=True, nullable=True, index=True)
    role = db.Column(db.String(20), nullable=False, default="creator")
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    email_verified = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)

    creator_profile = db.relationship(
        "CreatorProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    briefs = db.relationship("Brief", back_populates="brand")
    applications = db.relationship("Application", back_populates="creator")


class Specialization(db.Model):
    __tablename__ = "specializations"

    id = db.Column(db.Integer, Identity(), primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)


class ContentType(db.Model):
    __tablename__ = "content_types"

    id = db.Column(db.Integer, Identity(), primary_key=True)
    name = db.Column(db.String(60), unique=True, nullable=False)


class Skill(db.Model):
    __tablename__ = "skills"

    id = db.Column(db.Integer, Identity(), primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)


class Tool(db.Model):
    __tablename__ = "tools"

    id = db.Column(db.Integer, Identity(), primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    category = db.Column(db.String(80), default="")


class CreatorProfile(db.Model):
    __tablename__ = "creator_profiles"

    id = db.Column(db.Integer, Identity(), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    display_name = db.Column(db.String(100), nullable=False)
    headline = db.Column(db.String(180), default="")
    bio = db.Column(db.Text, default="")
    category = db.Column(db.String(80), default="AI Content Creator")
    skills = db.Column(db.Text, default="")
    tools = db.Column(db.Text, default="")
    starting_price = db.Column(db.Integer, nullable=False, default=0)
    verified = db.Column(db.Boolean, nullable=False, default=False)
    location = db.Column(db.String(100), default="")
    availability = db.Column(db.String(40), nullable=False, default="open")
    profile_url = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    user = db.relationship("User", back_populates="creator_profile")
    portfolio_items = db.relationship(
        "PortfolioItem", back_populates="creator_profile", cascade="all, delete-orphan"
    )
    specializations = db.relationship("Specialization", secondary=profile_specializations)
    content_types = db.relationship("ContentType", secondary=profile_content_types)
    skill_tags = db.relationship("Skill", secondary=profile_skills)
    tool_tags = db.relationship("Tool", secondary=profile_tools)
    verification_records = db.relationship(
        "VerificationRecord",
        primaryjoin="and_(CreatorProfile.id == foreign(VerificationRecord.subject_id), "
        "VerificationRecord.subject_type == 'profile')",
        viewonly=True,
    )


class PortfolioItem(db.Model):
    __tablename__ = "portfolio_items"

    id = db.Column(db.Integer, Identity(), primary_key=True)
    creator_profile_id = db.Column(db.Integer, db.ForeignKey("creator_profiles.id"), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default="")
    image_url = db.Column(db.String(500), default="")
    project_url = db.Column(db.String(500), default="")
    media_type = db.Column(db.String(40), nullable=False, default="video")
    specialization = db.Column(db.String(80), default="")
    preview_url = db.Column(db.String(500), default="")
    project_role = db.Column(db.String(180), default="")
    workflow_summary = db.Column(db.Text, default="")
    format = db.Column(db.String(80), default="")
    aspect_ratio = db.Column(db.String(30), default="")
    commercial_use = db.Column(db.String(150), default="Not specified")
    year = db.Column(db.Integer)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    creator_profile = db.relationship("CreatorProfile", back_populates="portfolio_items")
    skill_tags = db.relationship("Skill", secondary=portfolio_skills)
    tool_tags = db.relationship("Tool", secondary=portfolio_tools)
    verification_records = db.relationship(
        "VerificationRecord",
        primaryjoin="and_(PortfolioItem.id == foreign(VerificationRecord.subject_id), "
        "VerificationRecord.subject_type == 'portfolio')",
        viewonly=True,
    )


class VerificationRecord(db.Model):
    __tablename__ = "verification_records"
    __table_args__ = (
        CheckConstraint("status IN ('unverified', 'pending', 'verified')", name="ck_verification_status"),
    )

    id = db.Column(db.Integer, Identity(), primary_key=True)
    subject_type = db.Column(db.String(30), nullable=False)
    subject_id = db.Column(db.Integer, nullable=False, index=True)
    claim_type = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="unverified")
    evidence_note = db.Column(db.String(500), default="")
    evidence_reference = db.Column(db.String(500), default="")
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    reviewer = db.relationship("User", foreign_keys=[reviewer_id])


class Brief(db.Model):
    __tablename__ = "briefs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'open', 'paused', 'closed', 'completed')",
            name="ck_brief_status",
        ),
    )

    id = db.Column(db.Integer, Identity(), primary_key=True)
    brand_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    category = db.Column(db.String(80), default="Any")
    budget = db.Column(db.Integer, nullable=False, default=0)
    aspect_ratio = db.Column(db.String(30), default="9:16")
    commercial_use = db.Column(db.String(150), default="Social media")
    usage_duration = db.Column(db.String(80), default="30 days")
    territory = db.Column(db.String(100), default="India")
    status = db.Column(db.String(30), nullable=False, default="open")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    goal = db.Column(db.Text, default="")
    audience = db.Column(db.String(300), default="")
    requirements = db.Column(db.Text, default="")
    style = db.Column(db.String(300), default="")
    content_type = db.Column(db.String(60), default="video")
    deliverables = db.Column(db.Text, default="")
    format = db.Column(db.String(100), default="")
    duration = db.Column(db.String(80), default="")
    quantity = db.Column(db.Integer, nullable=False, default=1)
    timeline = db.Column(db.String(120), default="")
    deadline = db.Column(db.Date)
    licensing_type = db.Column(db.String(40), default="organic_only")
    exclusivity = db.Column(db.String(100), default="none")
    allow_edits = db.Column(db.Boolean, nullable=False, default=False)
    is_demo = db.Column(db.Boolean, nullable=False, default=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    brand = db.relationship("User", back_populates="briefs")
    applications = db.relationship("Application", back_populates="brief", cascade="all, delete-orphan")
    required_skills = db.relationship("Skill", secondary=brief_skills)
    preferred_tools = db.relationship("Tool", secondary=brief_tools)
    required_specializations = db.relationship("Specialization", secondary=brief_specializations)


class Application(db.Model):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("creator_id", "brief_id", name="unique_creator_application"),
        CheckConstraint(
            "status IN ('applied', 'shortlisted', 'accepted', 'declined')",
            name="ck_application_status",
        ),
    )

    id = db.Column(db.Integer, Identity(), primary_key=True)
    creator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    brief_id = db.Column(db.Integer, db.ForeignKey("briefs.id"), nullable=False)
    message = db.Column(db.Text, default="")
    status = db.Column(db.String(30), nullable=False, default="applied")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    creator = db.relationship("User", back_populates="applications")
    brief = db.relationship("Brief", back_populates="applications")
    engagement = db.relationship("Engagement", back_populates="application", uselist=False)


class Engagement(db.Model):
    __tablename__ = "engagements"
    __table_args__ = (
        CheckConstraint(
            "status IN ('accepted', 'in_progress', 'submitted', 'revision_requested', "
            "'approved', 'completed')",
            name="ck_engagement_status",
        ),
    )

    id = db.Column(db.Integer, Identity(), primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey("applications.id"), unique=True, nullable=False)
    status = db.Column(db.String(30), nullable=False, default="accepted")
    started_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    application = db.relationship("Application", back_populates="engagement")
    deliveries = db.relationship(
        "Delivery", back_populates="engagement", cascade="all, delete-orphan", order_by="Delivery.id"
    )
    events = db.relationship(
        "EngagementEvent",
        back_populates="engagement",
        cascade="all, delete-orphan",
        order_by="EngagementEvent.id",
    )


class Delivery(db.Model):
    __tablename__ = "deliveries"

    id = db.Column(db.Integer, Identity(), primary_key=True)
    engagement_id = db.Column(db.Integer, db.ForeignKey("engagements.id"), nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    link = db.Column(db.String(1000), nullable=False)
    note = db.Column(db.Text, default="")
    feedback = db.Column(db.Text, default="")
    revision_number = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(30), nullable=False, default="submitted")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    engagement = db.relationship("Engagement", back_populates="deliveries")
    submitted_by = db.relationship("User")


class EngagementEvent(db.Model):
    __tablename__ = "engagement_events"

    id = db.Column(db.Integer, Identity(), primary_key=True)
    engagement_id = db.Column(db.Integer, db.ForeignKey("engagements.id"), nullable=False)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)
    note = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    engagement = db.relationship("Engagement", back_populates="events")
    actor = db.relationship("User")
