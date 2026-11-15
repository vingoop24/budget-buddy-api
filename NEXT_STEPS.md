# BFF (Budget Financial Friend) — Roadmap

BFF (Budget Financial Friend) is an AI-powered personal finance app: a FastAPI + SQLite backend (this repo) and a React Native / Expo mobile client ([budget-buddy-mobile](https://github.com/vingoop24/budget-buddy-mobile)).

## Where it stands

- 20 REST endpoints with 19 passing pytest API tests
- 7-screen mobile app: home, expenses, budget, assistant, receipt scan, new/edit expense
- Receipt scanning with an OpenAI vision model (currently `gpt-5.4-mini`, chosen over `gpt-4o-mini` after a side-by-side test of accuracy and speed): output constrained by a strict JSON schema (OpenAI Structured Outputs), field-level normalization, and a review step that flags fields the model couldn't read before anything is saved
- Monthly budgets and per-category limits, with alerts at 80% (warning) and 100% (over)
- Monthly spending trends and AI-generated spending insights

The order below puts what other people need to use the app (accounts, hosting) before the beta and the analytics that depend on it.

## Phase 0 — Fix and tighten what's built

- [x] Only alert when a save crosses 80% or 100%, instead of on every save past the threshold
- [x] Allow category names containing `/` in category-limit endpoints
- [ ] End-to-end test of category limits, alerts and trends (web done, 12/12; phone check pending)
- [x] Receipt parsing with OpenAI Structured Outputs (strict JSON schema)
- [x] One product name across app and docs: BFF (Budget Financial Friend); the GitHub repos keep their budget-buddy-* names

## Phase 1 — Plan it like a product

- [ ] One-page product requirements doc: problem, target user (students on a budget), goals, scope, non-goals, risks
- [ ] Backlog, sprints, and roadmap tracked in Jira, with docs in Confluence
- [ ] Define product metrics: expenses logged per user per week, share of expenses entered by receipt scan, scan success rate, weekly active users
- [ ] Event logging so those metrics can be measured: expense added (manual or scan), scan completed, and which scanned fields the user corrected

## Phase 2 — Prove scan accuracy

- [ ] Accuracy benchmark in the repo: 30–50 receipts with labeled merchant, date, total and category; one command scores each field per model and prompt, with cost and latency
- [ ] Iterate on the prompt and model, then re-measure and record the improvement
- [ ] Measure accuracy from real use: compare what the scan extracted with what the user confirmed in the review step
- [ ] Keep real receipts private (gitignored or anonymized)

## Phase 3 — Make it usable by others

- [ ] User accounts, with expenses, budgets and limits scoped per user
- [ ] Move from SQLite to Postgres, with schema migrations
- [ ] Deploy the API to AWS (App Runner), with receipt images in S3
- [ ] Protect the AI endpoints: per-user rate limits and a locked-down CORS policy

## Phase 4 — Beta

- [ ] Beta with 5–10 testers (Android internal testing or TestFlight); short interviews; prioritize and ship the top fixes
- [ ] Report the first real product metrics

## Phase 5 — Analytics

- [ ] SQL analytics on Postgres: budget vs. actual by category, top merchants, and month-over-month change using joins, `GROUP BY`, and window functions
- [ ] Anonymized sample-data export and a spending dashboard in Tableau Public
- [ ] Detect recurring subscriptions and flag unusual charges

## Phase 6 — Automation

- [ ] Push notifications when budget alerts fire
- [ ] Weekly spending summary email (possibly as an n8n workflow)

## Polish

- [ ] README screenshots or GIF, architecture diagram, and setup instructions
- [ ] 60-second demo video
- [ ] Publish accuracy and usage results here as they come in
