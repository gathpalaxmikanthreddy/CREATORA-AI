import os
from datetime import date, timedelta

import click
from werkzeug.security import generate_password_hash

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


CREATORS = [
    {
        "name": "Mira Sen",
        "email": "mira@demo.creatora.test",
        "headline": "AI filmmaker crafting tactile, cinematic worlds",
        "bio": "Demo creator · A filmmaker exploring the meeting point of practical art direction and generative motion.",
        "category": "AI Filmmaking",
        "location": "Mumbai, India",
        "specializations": ["AI Filmmaking", "Product Storytelling"],
        "content_types": ["Video", "Animation"],
        "skills": ["Art Direction", "AI Video", "Compositing", "Color Grading"],
        "tools": ["Runway Gen-3", "Midjourney", "DaVinci Resolve"],
        "projects": [
            ("Monsoon in a Bottle", "A sensory product film about the first rain.", "Video", "9:16", "Runway Gen-3, Midjourney, DaVinci Resolve", "Art direction, AI video, color grading", "Built a tactile visual treatment; iterated image references, animated selected shots, then finished grade and sound by hand.", "Paid use subject to client license"),
            ("Soft Geometry", "An abstract motion study for a design studio.", "Animation", "1:1", "Runway Gen-3, After Effects", "Motion design, Compositing", "Generated shape studies, composited passes, and tuned timing with manual keyframes.", "Concept work · no commercial license"),
        ],
    },
    {
        "name": "Arjun Rao",
        "email": "arjun@demo.creatora.test",
        "headline": "Generative artist building impossible architecture",
        "bio": "Demo creator · I develop visual systems and AI-assisted worlds for culture, fashion, and design.",
        "category": "Generative Art",
        "location": "Bengaluru, India",
        "specializations": ["Generative Art", "Worldbuilding"],
        "content_types": ["Image", "Graphics"],
        "skills": ["Prompt Design", "Visual Research", "Image Editing"],
        "tools": ["Midjourney", "Photoshop", "ComfyUI"],
        "projects": [
            ("The Floating Archive", "A speculative image series imagining a library above the clouds.", "Image", "4:5", "Midjourney, Photoshop, ComfyUI", "Prompt design, visual research", "Mapped a visual reference system, generated controlled variations, and retouched the final frames.", "Portfolio concept · not licensed for ads"),
            ("Future Forms", "Graphic explorations for a contemporary furniture label.", "Graphics", "3:2", "ComfyUI, Photoshop", "Image editing, Art direction", "Used a custom node workflow for material and light explorations, then built production-ready layouts.", "Client-approved organic use"),
        ],
    },
    {
        "name": "Zoya Ahmed",
        "email": "zoya@demo.creatora.test",
        "headline": "AI animator with a soft spot for the surreal",
        "bio": "Demo creator · Character-led animation and playful motion systems for brands with a point of view.",
        "category": "AI Animation",
        "location": "Delhi, India",
        "specializations": ["AI Animation", "Character Design"],
        "content_types": ["Animation", "Video"],
        "skills": ["Character Design", "Motion Design", "Storyboarding"],
        "tools": ["Blender", "Runway Gen-3", "After Effects"],
        "projects": [
            ("A Tiny Big Day", "A short character animation about an everyday celebration.", "Animation", "16:9", "Blender, Runway Gen-3, After Effects", "Character design, storyboarding", "Storyboarded beats, created character motion, then blended generated environments with hand-composited animation.", "Paid advertising by separate agreement"),
            ("Cloud Parade", "A loopable motion piece for an independent music release.", "Video", "1:1", "Runway Gen-3, After Effects", "Motion design, Compositing", "Explored frame-consistent cloud forms and stitched the final loop with a manual finishing pass.", "Personal demo project"),
        ],
    },
    {
        "name": "Kabir Iyer",
        "email": "kabir@demo.creatora.test",
        "headline": "Synthetic nature, grounded in thoughtful craft",
        "bio": "Demo creator · I combine generative imagery with careful compositing for lifestyle and travel stories.",
        "category": "Generative Content",
        "location": "Chennai, India",
        "specializations": ["Generative Art", "Product Storytelling"],
        "content_types": ["Image", "Video"],
        "skills": ["Art Direction", "Compositing", "Creative Strategy"],
        "tools": ["Stable Diffusion XL", "ComfyUI", "Photoshop"],
        "projects": [
            ("Wild Quiet", "A set of editorial landscapes for a mindful travel concept.", "Image", "3:2", "Stable Diffusion XL, ComfyUI, Photoshop", "Art direction, compositing", "Built a repeatable node graph for lighting and atmosphere, then composited foreground details.", "Editorial concept · usage to be agreed"),
            ("Coastline / Memory", "A moving postcard from an imagined shoreline.", "Video", "9:16", "ComfyUI, Runway Gen-3", "Creative strategy, AI video", "Created a reference board, tested transitions, and manually selected and edited clips for continuity.", "Client-approved commercial use"),
        ],
    },
    {
        "name": "Leela Thomas",
        "email": "leela@demo.creatora.test",
        "headline": "Design-led AI visuals for thoughtful launches",
        "bio": "Demo creator · Brand designer exploring how generative imagery can support a clear visual system.",
        "category": "AI Brand Design",
        "location": "Kochi, India",
        "specializations": ["AI Brand Design", "Generative Art"],
        "content_types": ["Graphics", "Image"],
        "skills": ["Brand Design", "Typography", "Art Direction"],
        "tools": ["Adobe Firefly", "Illustrator", "Figma"],
        "projects": [
            ("Good Ground", "A warm visual identity study for a local food collective.", "Graphics", "4:5", "Adobe Firefly, Illustrator, Figma", "Brand design, typography", "Generated texture explorations, refined vector marks, and checked the system across social layouts.", "Organic social use only"),
            ("A Table for All", "Editorial still-life direction for a shared-meal campaign.", "Image", "4:5", "Adobe Firefly, Photoshop", "Art direction, image editing", "Used Firefly for early prop studies and rebuilt the selected composition with licensed source assets.", "Paid use for 12 months by agreement"),
        ],
    },
    {
        "name": "Dev Malhotra",
        "email": "dev@demo.creatora.test",
        "headline": "A motion designer making AI feel human",
        "bio": "Demo creator · Short-form motion, typography, and AI-assisted transitions for digital-first brands.",
        "category": "Motion Design",
        "location": "Pune, India",
        "specializations": ["Motion Design", "AI Filmmaking"],
        "content_types": ["Video", "Graphics"],
        "skills": ["Typography", "Motion Design", "Editing"],
        "tools": ["After Effects", "Runway Gen-3", "ElevenLabs"],
        "projects": [
            ("Type in Motion", "A kinetic typography package for a community event.", "Graphics", "16:9", "After Effects, Runway Gen-3", "Typography, motion design", "Designed type treatments first, then used generated transitions as supporting texture rather than the message.", "Demo work · no client license"),
            ("Voices of Tomorrow", "A short-form film concept pairing human voices and abstract movement.", "Video", "9:16", "Runway Gen-3, After Effects, ElevenLabs", "Editing, motion design", "Started with a human-authored script, tested visual motifs, then edited and mixed a short vertical piece.", "Organic and paid usage by agreement"),
        ],
    },
]


def get_tag(model, name, category=None):
    tag = model.query.filter(db.func.lower(model.name) == name.lower()).first()
    if tag is None:
        kwargs = {"name": name}
        if category is not None:
            kwargs["category"] = category
        tag = model(**kwargs)
        db.session.add(tag)
        db.session.flush()
    return tag


def get_demo_user(email, name, role, password):
    user = User.query.filter_by(email=email).first()
    if user:
        if not user.is_demo:
            raise click.ClickException(
                f"{email} already belongs to a non-demo account; no data was changed."
            )
        return user, False
    user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
        role=role,
        is_demo=True,
    )
    db.session.add(user)
    db.session.flush()
    return user, True


def register_seed_command(application):
    @application.cli.command("seed-demo")
    @click.option(
        "--password",
        envvar="DEMO_PASSWORD",
        default="CreatorDemo!2026",
        show_default=False,
        help="Password for newly created local demo accounts.",
    )
    def seed_demo_command(password):
        """Add safe, idempotent local showcase data; never reset the database."""
        if len(password) < 12:
            raise click.ClickException("Demo password must be at least 12 characters.")

        counts = {"users": 0, "profiles": 0, "portfolio_items": 0, "briefs": 0, "applications": 0}
        try:
            creators = []
            for data in CREATORS:
                user, created = get_demo_user(data["email"], data["name"], "creator", password)
                counts["users"] += int(created)
                profile = CreatorProfile.query.filter_by(user_id=user.id).first()
                if profile is None:
                    profile = CreatorProfile(display_name=data["name"], user=user)
                    db.session.add(profile)
                    db.session.flush()
                    counts["profiles"] += 1
                profile.display_name = data["name"]
                profile.headline = data["headline"]
                profile.bio = data["bio"]
                profile.category = data["category"]
                profile.location = data["location"]
                profile.availability = "limited" if data["name"] == "Dev Malhotra" else "open"
                profile.starting_price = 18000 + (len(creators) * 4500)
                profile.specializations = [get_tag(Specialization, name) for name in data["specializations"]]
                profile.content_types = [get_tag(ContentType, name) for name in data["content_types"]]
                profile.skill_tags = [get_tag(Skill, name) for name in data["skills"]]
                profile.tool_tags = [get_tag(Tool, name, "creative") for name in data["tools"]]
                profile.skills = ", ".join(data["skills"])
                profile.tools = ", ".join(data["tools"])
                creators.append((user, profile, data))

            brand, created = get_demo_user(
                "brand@demo.creatora.test", "Good Things Studio (Demo)", "brand", password
            )
            counts["users"] += int(created)
            db.session.flush()

            portfolio_items = []
            for user, profile, data in creators:
                for index, project in enumerate(data["projects"], start=1):
                    title, description, media, ratio, tools, skills, workflow, rights = project
                    item = PortfolioItem.query.filter_by(
                        creator_profile_id=profile.id, title=title
                    ).first()
                    if item is None:
                        item = PortfolioItem(creator_profile=profile, title=title)
                        db.session.add(item)
                        db.session.flush()
                        counts["portfolio_items"] += 1
                    item.description = f"DEMO SAMPLE · {description}"
                    item.media_type = media.lower()
                    item.specialization = data["category"]
                    item.format = "Social campaign" if media in {"Video", "Animation"} else "Digital editorial"
                    item.aspect_ratio = ratio
                    item.project_role = "Creative direction, AI workflow, and finishing"
                    item.workflow_summary = workflow
                    item.commercial_use = rights
                    item.year = 2026
                    item.tool_tags = [get_tag(Tool, name.strip(), "creative") for name in tools.split(",")]
                    item.skill_tags = [get_tag(Skill, name.strip()) for name in skills.split(",")]
                    portfolio_items.append(item)

            brief_specs = [
                {
                    "title": "DEMO · Monsoon coffee launch film",
                    "goal": "Introduce a seasonal cold-brew range with a memorable, tactile short film.",
                    "audience": "Urban coffee drinkers and design-conscious young professionals.",
                    "description": "Create a playful vertical launch film that makes monsoon coffee feel vivid, sensory, and shareable.",
                    "requirements": "Use brand colors and product pack reference; avoid unsupported product claims.",
                    "style": "Playful, cinematic, rich natural textures.",
                    "content_type": "video",
                    "deliverables": "Hero film and two short cutdowns",
                    "format": "Instagram Reels",
                    "aspect_ratio": "9:16",
                    "duration": "15-30 seconds",
                    "quantity": 3,
                    "budget": 55000,
                    "timeline": "Three weeks after kickoff",
                    "deadline": date.today() + timedelta(days=28),
                    "commercial_use": "paid_ads",
                    "usage_duration": "6 months",
                    "territory": "India",
                    "exclusivity": "category",
                    "allow_edits": True,
                    "category": "AI Filmmaking",
                    "skills": ["AI Video", "Art Direction"],
                    "specializations": ["AI Filmmaking"],
                    "tools": ["Runway Gen-3"],
                    "status": "open",
                },
                {
                    "title": "DEMO · Dreamlike animation for a music release",
                    "goal": "Build anticipation for an independent artist's new single.",
                    "audience": "Listeners who discover emerging music through social video.",
                    "description": "A loopable animation with a distinctive character and a dreamy, hand-made feeling.",
                    "requirements": "Deliver one master loop and a clean version without text.",
                    "style": "Surreal, warm, quietly playful.",
                    "content_type": "animation",
                    "deliverables": "One loop and one clean export",
                    "format": "Social and streaming canvases",
                    "aspect_ratio": "1:1",
                    "duration": "8 seconds, seamless loop",
                    "quantity": 2,
                    "budget": 32000,
                    "timeline": "Two weeks",
                    "deadline": date.today() + timedelta(days=35),
                    "commercial_use": "organic_and_paid",
                    "usage_duration": "12 months",
                    "territory": "Worldwide",
                    "exclusivity": "none",
                    "allow_edits": False,
                    "category": "AI Animation",
                    "skills": ["Motion Design", "Storyboarding"],
                    "specializations": ["AI Animation"],
                    "tools": ["After Effects"],
                    "status": "open",
                },
                {
                    "title": "DEMO · A new visual world for a mindful stay",
                    "goal": "Create a bank of on-brand stills for a boutique hospitality launch.",
                    "audience": "Travelers looking for slower, design-forward experiences.",
                    "description": "Develop an editorial set of generative images that communicates calm, place, and human warmth.",
                    "requirements": "Supply selected finals plus a concise workflow and source-asset note.",
                    "style": "Natural, grounded, soft light.",
                    "content_type": "image",
                    "deliverables": "Six campaign stills",
                    "format": "Web and social",
                    "aspect_ratio": "4:5",
                    "duration": "Still imagery",
                    "quantity": 6,
                    "budget": 40000,
                    "timeline": "Four weeks",
                    "deadline": date.today() + timedelta(days=42),
                    "commercial_use": "organic_only",
                    "usage_duration": "90 days",
                    "territory": "India",
                    "exclusivity": "custom",
                    "allow_edits": False,
                    "category": "Generative Content",
                    "skills": ["Image Editing", "Visual Research"],
                    "specializations": ["Generative Art"],
                    "tools": ["ComfyUI"],
                    "status": "open",
                },
                {
                    "title": "DEMO · Motion graphics for a community event",
                    "goal": "Give a neighborhood creative festival a recognizable animated identity.",
                    "audience": "Local artists, makers, and event visitors.",
                    "description": "Create flexible kinetic type and social graphics with room for event details.",
                    "requirements": "Supply an editable project handoff and two aspect ratios.",
                    "style": "Bold type, vivid color, friendly energy.",
                    "content_type": "graphics",
                    "deliverables": "Animated title, three social cards",
                    "format": "Social campaign",
                    "aspect_ratio": "16:9 and 1:1",
                    "duration": "10 second loop",
                    "quantity": 4,
                    "budget": 28000,
                    "timeline": "Two weeks",
                    "deadline": date.today() + timedelta(days=50),
                    "commercial_use": "internal",
                    "usage_duration": "Event campaign only",
                    "territory": "India",
                    "exclusivity": "none",
                    "allow_edits": True,
                    "category": "Motion Design",
                    "skills": ["Typography", "Motion Design"],
                    "specializations": ["Motion Design"],
                    "tools": ["After Effects"],
                    "status": "paused",
                },
            ]
            briefs = []
            for data in brief_specs:
                brief = Brief.query.filter_by(brand_id=brand.id, title=data["title"]).first()
                if brief is None:
                    brief = Brief(
                        brand=brand,
                        title=data["title"],
                        description=data["description"],
                    )
                    db.session.add(brief)
                    db.session.flush()
                    counts["briefs"] += 1
                for key in (
                    "goal", "audience", "description", "requirements", "style", "content_type",
                    "deliverables", "format", "aspect_ratio", "duration", "quantity", "budget",
                    "timeline", "deadline", "commercial_use", "usage_duration", "territory",
                    "exclusivity", "allow_edits", "category", "status",
                ):
                    setattr(brief, key, data[key])
                brief.is_demo = True
                brief.required_skills = [get_tag(Skill, name) for name in data["skills"]]
                brief.required_specializations = [
                    get_tag(Specialization, name) for name in data["specializations"]
                ]
                brief.preferred_tools = [get_tag(Tool, name, "creative") for name in data["tools"]]
                briefs.append(brief)

            db.session.flush()
            demo_items_by_title = {item.title: item for item in portfolio_items}
            verified_samples = [
                (creators[0][1], "profile", "tools", "verified", "Demo-only sample signal; tool receipts are represented by fictional showcase evidence."),
                (demo_items_by_title.get("Monsoon in a Bottle"), "portfolio", "workflow", "verified", "Demo-only sample signal; fictional workflow review for challenge walkthrough."),
                (demo_items_by_title.get("The Floating Archive"), "portfolio", "past_work", "verified", "Demo-only sample signal; fictional sample project review."),
                (creators[5][1], "profile", "workflow", "pending", "Demo-only sample signal; sample workflow claim awaits review."),
            ]
            for subject, subject_type, claim_type, status, evidence in verified_samples:
                if subject is None:
                    continue
                exists = VerificationRecord.query.filter_by(
                    subject_type=subject_type,
                    subject_id=subject.id,
                    claim_type=claim_type,
                    is_demo=True,
                ).first()
                if exists is None:
                    db.session.add(
                        VerificationRecord(
                            subject_type=subject_type,
                            subject_id=subject.id,
                            claim_type=claim_type,
                            status=status,
                            evidence_note=evidence,
                            reviewer_id=None,
                            reviewed_at=db.func.current_timestamp(),
                            is_demo=True,
                        )
                    )

            def seed_application(brief, creator, status, message):
                application = Application.query.filter_by(
                    brief_id=brief.id, creator_id=creator.id
                ).first()
                if application is None:
                    application = Application(
                        brief=brief,
                        creator=creator,
                        status=status,
                        message=message,
                    )
                    db.session.add(application)
                    db.session.flush()
                    counts["applications"] += 1
                return application

            accepted_revise = seed_application(
                briefs[0], creators[0][0], "accepted",
                "I'd shape this around tactile macro textures and a deliberate color journey.",
            )
            accepted_approved = seed_application(
                briefs[1], creators[2][0], "accepted",
                "I can develop the character animation and a seamless short-form loop.",
            )
            seed_application(
                briefs[2], creators[1][0], "shortlisted",
                "My visual research process could bring a coherent image set to this brief.",
            )
            seed_application(
                briefs[0], creators[5][0], "applied",
                "I can explore a type-led cutdown and motion toolkit for the launch.",
            )

            for application, status, delivery_status, event_name, note in [
                (
                    accepted_revise,
                    "revision_requested",
                    "revision_requested",
                    "revision_requested",
                    "Demo review asks for a clearer pack shot in the closing frame.",
                ),
                (
                    accepted_approved,
                    "approved",
                    "approved",
                    "delivery_approved",
                    "Demo sample delivery approved by the brand.",
                ),
            ]:
                engagement = Engagement.query.filter_by(application_id=application.id).first()
                if engagement is None:
                    engagement = Engagement(application=application, status=status)
                    db.session.add(engagement)
                    db.session.flush()
                engagement.status = status
                if not engagement.deliveries:
                    db.session.add(
                        Delivery(
                            engagement=engagement,
                            submitted_by=application.creator,
                            link="https://example.com/",
                            note="DEMO SAMPLE · Placeholder delivery link; use this record to walk through the review flow.",
                            feedback=note if status == "revision_requested" else "",
                            revision_number=0,
                            status=delivery_status,
                        )
                    )
                if not engagement.events:
                    db.session.add(
                        EngagementEvent(
                            engagement=engagement,
                            actor=brand,
                            event_type=event_name,
                            note=note,
                        )
                    )

            db.session.commit()
        except Exception:
            db.session.rollback()
            raise

        click.echo("Demo data added safely (existing records were not deleted or reset).")
        click.echo(f"New records: {counts}")
        click.echo(f"Demo password: {password}")
        click.echo("Brand: brand@demo.creatora.test")
        click.echo("Creators: mira@demo.creatora.test, arjun@demo.creatora.test, zoya@demo.creatora.test,")
        click.echo("          kabir@demo.creatora.test, leela@demo.creatora.test, dev@demo.creatora.test")
    return seed_demo_command
