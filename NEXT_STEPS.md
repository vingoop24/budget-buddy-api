# Budget Friend — Roadmap

Budget Friend is an AI-powered personal finance app: a FastAPI + SQLite backend (this repo) and a React Native / Expo mobile client ([budget-buddy-mobile](https://github.com/vingoop24/budget-buddy-mobile)).

## Where it stands

- 20 REST endpoints with 17 passing pytest API tests
- 7-screen mobile app: home, expenses, budget, assistant, receipt scan, new/edit expense
- Receipt scanning with GPT-4o-mini vision: a prompt that returns JSON, validated against a schema, with a review step before saving
- Monthly budgets and per-category limits, with alerts at 80% (warning) and 100% (over)
- Monthly spending trends and AI-generated spending insights

## Phase 1 — Plan it like a product

- [ ] One-page product requirements doc: problem, target user (students on a budget), goals, scope, non-goals, risks
- [ ] Backlog, sprints, and roadmap tracked in Jira, with docs in Confluence
- [ ] Define product metrics: expenses logged per user per week, share of expenses entered by receipt scan, scan success rate, weekly active users

## Phase 2 — Prove it works

- [ ] Receipt-scan accuracy benchmark: 30–50 real receipts with known merchant, date, total, and category, scored field by field
- [ ] Iterate on the prompt and model, then re-measure and record the improvement
- [ ] Beta with 5–10 testers via Expo Go or TestFlight; short interviews; prioritize the top fixes

## Phase 3 — Analytics

- [ ] SQL-based analytics: rewrite trends and add budget vs. actual by category, top merchants, and month-over-month change using joins, `GROUP BY`, and window functions
- [ ] Spending dashboard in Tableau Public using sample data

## Phase 4 — Automation and cloud

- [ ] Push or email notifications when budget alerts fire, plus a weekly spending summary (possibly as an n8n workflow)
- [ ] Deploy the API to AWS (App Runner or Lambda + API Gateway) and move from SQLite to Postgres
- [ ] Detect recurring subscriptions and flag unusual charges

## Polish

- [ ] README screenshots or GIF, architecture diagram, and setup instructions
- [ ] 60-second demo video
- [ ] Publish accuracy and usage results here as they come in
