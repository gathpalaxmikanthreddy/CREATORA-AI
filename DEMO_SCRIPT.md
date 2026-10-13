# Creatora AI — 2–3 minute demo

## Live walkthrough (about 2½ minutes)

1. **0:00–0:20 · Introduce the marketplace.** Open Home, point out the creator directory, project briefs, and the brand/creator paths. The evaluation emphasis is visible in the product: profiles/AI portfolios **30%**, discovery/filtering **25%**, briefs **20%**, UX **15%**, presentation **10%**.
2. **0:20–0:55 · Discover a creator as a brand.** Log in as `brand@demo.creatora.test` with `CreatorDemo!2026`, open **Find creators**, combine the skills, specialization, tool, content type, location, or availability filters, and point out the result count and clear-filter action. Open Mira Sen's profile and a portfolio detail to show tool/model, skill, aspect ratio, role, workflow, and commercial-use notes. Call out that seed verification labels explicitly say **Demo sample**.
3. **0:55–1:30 · Create a brief.** From the brand dashboard, open **Build a brief from an idea**. Enter a rough campaign idea and use the local suggested structure. Explain that it is rules-based (not an LLM), needs no API key, and every field can be edited. Review the audience, deliverables, content type, format, budget, timeline, usage term, territory, exclusivity, and edit permission; publish.
4. **1:30–2:00 · Apply as a creator.** Log out and log in as `mira@demo.creatora.test` using the same local demo password. Open the published brief, add a short proposal, and apply. The dashboard tracks application status.
5. **2:00–2:30 · Show an engagement.** Log back in as the brand and shortlist/accept the application from the brief's application review. Re-enter as that creator to start work and submit a delivery URL plus note. As brand, request a revision with feedback; as creator, resubmit; then approve and mark complete. Use the already-seeded delivery/revision example if a quick review-state tour is preferred.

Seed sample delivery URLs point to `https://example.com/` as an explicit placeholder; the application demonstrates status handling, not hosted media. For an uninterrupted live end-to-end path, use a newly created brief/application and submit a real demo link you control.

## Demo logins

`flask --app app seed-demo` creates accounts only when absent and never resets the database. New demo accounts use `CreatorDemo!2026` by default; set `DEMO_PASSWORD` or pass `--password` to choose another local password. The seed process will refuse to take over an existing non-demo email. Account list and setup details are in `README.md`.

When Supabase Auth is enabled, the seed command creates marketplace showcase records only; it does not create Supabase Auth identities. Use the registration page to create your test brand and creator sign-ins. If email confirmation is enabled, confirm each address before logging in. Seeded showcase profiles and briefs are public and can be browsed without using the local demo passwords.

To demonstrate the protected admin dashboard, create a local admin with `flask --app app create-admin`, or promote an existing active, verified account with `flask --app app promote-admin EMAIL`, then open `/admin/login`.

## Judge presentation outline

1. **The opportunity:** AI-native creators need a way to explain craft and workflow, not just output.
2. **Discovery:** normalized profile/portfolio skills and tools make combined search meaningful.
3. **Brief quality:** clear deliverables, creative direction, budget, formats, and licensing requirements.
4. **Trust & delivery:** transparent verification status plus application, feedback, revisions, and approval history.
5. **Prototype boundaries:** media is externally linked rather than uploaded; the brief helper is transparent rules-based assistance, not an LLM; demo verification is fictional and clearly labeled.
