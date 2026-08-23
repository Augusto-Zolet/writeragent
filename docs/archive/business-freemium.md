# Business freemium features

**Status:** Product planning (not implemented)  
**Last updated:** 2026-07-09  
**Audience:** product, architecture, go-to-market  

This document describes **business-oriented freemium** offerings for WriterAgent. It is deliberately scoped to **net-new** capabilities.

## Enterprise-only lens

Paid features must pass a simple filter: **would a typical solo LibreOffice user care?** If yes, it belongs in the free extension—not behind a business SKU.

| Audience | What they want | Paid tier relevance |
|----------|----------------|---------------------|
| **Normal / solo users** | Chat, tools, BYO keys, local models, personal folder search, scripting, MCP DIY | **None required.** They should never feel nudged toward a subscription for day-to-day work. |
| **Large enterprises** | Fleet control, compliance evidence, identity lifecycle, shared org knowledge with ACLs, procurement-friendly contracts | **This is the freemium target.** |

Freemium is therefore **not** “better AI for individuals.” It is **org plumbing**—the controls, shared assets, and vendor paperwork IT and legal need when rolling agents to hundreds of seats. Power users who happen to work alone keep the full free product; enterprises pay for governance at scale.

Optional **Cloud Credits** (hosted inference without API keys) may appeal to non-enterprise users as a convenience SKU, but it is **orthogonal** to the core business freemium story and must not become a paywall on tools or models users can already run locally with BYO keys.

## Non-negotiable product rule

| Rule | Meaning |
|------|---------|
| **Existing features stay free** | Everything WriterAgent already ships (sidebar chat, core and specialized tools, Writer/Calc/Draw/Impress paths, BYO API keys, local history, embeddings/vision/scripting/MCP as currently available, etc.) remains available without a paid seat or paywall. |
| **Freemium = new layers** | Paid value is **added** as services, admin/control plane, collaboration, vertical packs, and support—not by locking current tools behind a license. |
| **Enterprise-only paid scope** | New paid capabilities target **large-org problems** (fleet policy, compliance evidence, SSO, multi-user ACL knowledge). Capabilities solo users would want belong in the free extension, not a “Pro” SKU. |
| **Local + BYO remains first-class** | Organizations that run their own keys or private OpenAI-compatible gateways must keep full agent capability on the free/open extension. |

**Implication:** Business freemium is mostly a **platform and packaging** story on top of the free LibreOffice extension, not an “open core with tools removed” story.

---

## Why businesses pay (and individuals often do not)

WriterAgent’s free surface already covers **doing work in LibreOffice with an agent**. Normal users get that entirely for free and have no reason to buy a seat. Procurement and IT fund capabilities that only matter when **many people, policies, and auditors** are involved:

| Buyer concern | What they will fund | Why solo users ignore it |
|---------------|---------------------|--------------------------|
| Cost control | Shared credit pools, model allowlists, spend caps | They manage their own key and spend |
| Risk / compliance | Audit logs, data residency, DPA, tool egress policy | No auditor asks for SIEM export of one laptop |
| Identity | SSO, offboarding, seat lifecycle | One local LibreOffice profile is enough |
| Scale | Multi-user knowledge bases, approved connectors, rollout channel | Personal folder FTS/embeddings already cover “my files” |
| Adoption | Vertical workflows, training, SLA | DIY with free tools is fine for one person |
| Differentiation | Brand/playbook agents that encode *their* process | Optional; free users can paste their own prompts |

None of those require removing free chat or free tools from the OXT. If a capability is genuinely useful to individuals, ship it free and sell **enterprise packaging** (multi-tenant admin, ACLs, audit ingest, SSO) around it—not the underlying agent behavior.

---

## Tier sketch (business-facing)

Names are provisional. Feature lists below are **additive** only. **Core freemium** (Team / Business / Enterprise) targets orgs; **Cloud Credits** is an optional convenience layer, not the main enterprise value prop.

```text
┌────────────────────────────────────────────────────────────┐
│  WriterAgent extension (current feature set)               │  always free
│  BYO keys / local models / full local agent                │  ← normal users stop here
└────────────────────────────────────────────────────────────┘
                            +
┌────────────────────────────┐  ┌────────────────────────────┐
│  Cloud Credits (optional)  │  │  Workflow / asset packs    │  optional SKUs
│  Hosted inference only     │  │  Templates, vertical jobs  │  (enterprise rollout)
└────────────────────────────┘  └────────────────────────────┘
                            +
┌────────────────────────────────────────────────────────────┐
│  Team / Business platform                                  │  ← freemium starts: multi-seat org
│  Org keys, admin defaults, shared RAG, light audit         │
└────────────────────────────────────────────────────────────┘
                            +
┌────────────────────────────────────────────────────────────┐
│  Enterprise platform                                       │  ← large-enterprise must-haves
│  SSO, policy matrix, private gateway, SLA, air-gap channel │
└────────────────────────────────────────────────────────────┘
```

| Tier | Primary buyer | What is new | Normal user? |
|------|---------------|-------------|--------------|
| **Community / Free** | Everyone | Today’s extension; no business control plane required | **Default.** No upsell for core work. |
| **Cloud Credits** | Convenience (any size) | Hosted LLM (and later hosted embeddings/search) with usage billing | Optional; BYO keys remain full-featured without it |
| **Team** | Multi-seat orgs (agencies, firms, IT pilots) | Seats, shared org keys/credits, admin defaults, shared prompt/style packs, project audit export | Irrelevant until you need *org* admin—not “pro AI” |
| **Business / Enterprise** | IT + compliance at scale | SSO, SCIM-class provisioning (later), full policy matrix, private endpoints, retention, DPA packet, SLA, air-gapped distribution | Procurement-only surface; solo users never need this |

Cloud Credits and Team can be sold independently of each other (org with own gateway may buy Team without Cloud Credits).

---

## Business freemium feature catalog

Each item is **new product surface** aimed at **enterprise-scale concerns** (fleet admin, compliance, multi-user knowledge, procurement). Free extension behavior must not regress if the user never signs into a business account.

**Inclusion test:** Before adding a paid line item, ask: *“Does this solve a problem only large organizations have?”* Examples that pass: SSO, seat offboarding, ACL-aware team RAG, SIEM export, DPA packet. Examples that fail: “more tools,” “better models,” “faster chat”—those stay free.

### 1. Organization control plane (Team+)

A web (or desktop-admin) **org console**, not a fork of the free tool registry.

| Capability | Description | Free extension without org |
|------------|-------------|----------------------------|
| **Seats** | Named users; invite/remove; seat counts for billing | N/A (single local user) |
| **Org API keys / credit pool** | One pool for the company; members do not paste personal keys into every profile | Local `writeragent.json` keys still work |
| **Admin defaults** | Default text/image models, max tool-loop depth *on hosted path*, region | User keeps full local settings |
| **Feature flags for paid modules** | Enable Team RAG, audit export, vertical packs for the org | Paid modules simply absent; existing tools unchanged |
| **Approved OXT channel** | Pin or recommend extension versions for the fleet | Users install from community releases as today |

**Monetization:** per-seat subscription (Team), volume seats (Enterprise).

---

### 2. Identity and access (Enterprise-first; Team light)

| Capability | Notes |
|------------|--------|
| **SSO (OIDC first)** | Login to control plane and optional extension “signed-in” session for org features |
| **Directory / SCIM (later)** | Auto-provision and deprovision seats |
| **Role model** | Admin / billing / member / auditor (read-only logs) |
| **Session policy** | Idle timeout for cloud session; does not disable offline free use |

**Monetization:** Enterprise SKU; optional SSO add-on for Team if demand appears early.

---

### 3. Shared knowledge and team RAG (Team+)

Distinct from **personal** folder FTS / embeddings already in the free product.

| Capability | Description |
|------------|-------------|
| **Org corpus** | Admin-scoped indexes over approved folders, DMS mounts, or sync roots |
| **ACL-aware retrieval** | Documents visible only to groups that should see them |
| **Curated collections** | “HR handbook”, “product specs”, “sales battlecards” as first-class corpora |
| **Reindex schedules & quotas** | Ops-friendly limits separate from a power user’s laptop index |
| **Citation policy** | Require sources in answers when corpus is used (org toggle) |

**Positioning:** Free users keep personal embeddings/FTS. Paid = **multi-user, admin-governed knowledge**, not “you must pay to index a folder.”

**Monetization:** included in Team above N seats, or metered by index size / queries.

---

### 4. Policy, security, and egress (Business / Enterprise)

New **policy engine** applied when the user is signed into an org (or when traffic goes through the org gateway). Offline free mode ignores org policy.

| Policy area | Examples |
|-------------|----------|
| **Model allowlist** | Only corporate gateway models |
| **Base URL allowlist** | Only approved OpenAI-compatible hosts |
| **Tool egress** | Disable or restrict web/agent-search, image gen, arbitrary MCP, outbound file paths |
| **Domain allowlists** | Web fetch only to `*.company.com` and approved research domains |
| **Data handling** | “No training” contract via private gateway; block third-party image hosts |
| **Document scope** | Optional: team projects only open files under managed roots |

**Monetization:** Enterprise core; subset of toggles may ship in Team (e.g. disable web for interns).

---

### 5. Audit, retention, and compliance (Business / Enterprise)

| Capability | Description |
|------------|-------------|
| **Action audit log** | Who ran which agent/tool, when, on which document identity (URL/title hash), model used, success/fail |
| **Export** | SIEM-friendly export (JSON/CSV), date range, per-project filters |
| **Retention policies** | 30/90/365-day cloud log retention; customer-owned storage option later |
| **Review queues (optional later)** | Manager approve/reject for high-risk tool classes (e.g. bulk rewrite) |
| **Vendor packet** | DPA, subprocessors list, security FAQ—procurement enablement, not code |

Free local debug logs (`writeragent_debug.log`) stay as developer-oriented local logging; they are **not** a substitute for org audit.

**Monetization:** Business/Enterprise; storage overage metering optional.

---

### 6. Private gateway and data residency (Enterprise)

| Capability | Description |
|------------|-------------|
| **WriterAgent-managed private proxy** | Org traffic to LLMs via a dedicated endpoint |
| **Customer-hosted gateway support** | Documented contract: extension talks only to customer URL with org auth |
| **Region pinning** | EU/US (etc.) for hosted components |
| **Air-gapped package** | Offline OXT + offline model guidance + license server for *paid platform features* only |

**Monetization:** Enterprise base + professional services for air-gap and custom deploy.

---

### 7. Integrations and managed connectors (Team+ / Enterprise)

Build **new** connectors and catalogs; do not paywall existing free MCP if already shipped to all users.

| Integration | Business value |
|-------------|----------------|
| **Managed MCP catalog** | IT-approved servers, signed config, version pin |
| **DMS / drive policies** | e.g. Nextcloud, SharePoint, Mayan-class EDMS roots for team RAG |
| **CRM / ticket fields → doc agents** | Sales and support verticals (see §8) |
| **SSO-linked extension config** | Pull org defaults after login without editing JSON by hand |

**Monetization:** connector packs; Enterprise includes a base catalog.

---

### 8. Vertical workflow packs (SKU add-ons)

Productized **jobs** for **org-wide rollout** (legal ops, finance close, sales enablement)—not shortcuts individuals cannot replicate with free tools. The pack is paid packaging (templates, guardrails, admin distribution); the primitives stay free for DIY power users.

| Pack | Example workflows | Likely LO surface | Enterprise angle |
|------|-------------------|-------------------|------------------|
| **Legal / professional** | Playbook rewrite, clause checklist, citation/footnote discipline, reviewable-edit batches | Writer | Firm-wide playbook enforcement |
| **Finance / ops** | Close checklist, variance narrative from sheets, standardized board pack tables | Calc + Writer | Standardized reporting across teams |
| **Sales / marketing** | Proposal from CRM fields, PPT-Master deck from brief, one-pagers | Writer + Impress | Approved templates pushed to reps |
| **Research / knowledge** | Corpus Q&A with mandatory citations, literature notes to structured docs | Writer + team RAG | Governed research over org corpus |
| **Support / CS** | Ticket → runbook document, escalation summary templates | Writer | Consistent support artifacts at scale |

**Monetization:** per-pack subscription or included in higher tiers; templates can start first-party only, later marketplace.

---

### 9. Collaboration surfaces (new; Team+)

| Capability | Description |
|------------|-------------|
| **Shared prompt / style libraries** | House voice, legal disclaimers, brand terms—org-managed, synced to clients |
| **Project workspaces** | Group chats/history metadata tied to a matter or client (cloud), separate from free per-document local history |
| **Co-review of agent edits (later)** | Multi-user accept/reject queue on top of free single-user reviewable edits |

Local single-user history remains free and offline-capable.

---

### 10. Support, success, and delivery (service SKUs)

| Offering | Content |
|----------|---------|
| **Team support** | Business-hours email/chat, install help |
| **Enterprise SLA** | Response times, named contact, severity definitions |
| **Onboarding** | Admin setup, policy templates, pilot cohort |
| **Training** | Power-user workshops (Writer redlines, Calc agents, deck generation) |
| **Custom librarian / onboarding content** | Org-specific agent guidance (paid content, not a core code lock) |

---

### 11. Optional Cloud Credits (orthogonal SKU)

Hosted inference (and later hosted embeddings / agent-search) so users never paste a key. **Positioned as convenience, not enterprise freemium core**—large enterprises often bring their own gateway anyway.

| Property | Rule |
|----------|------|
| **Does not replace free BYO** | Same tools and UIs work with customer keys |
| **Not a “Pro” tier for individuals** | No feature unlock; only hosted billing |
| **Free trial credits** | Optional conversion funnel; must not degrade BYO experience |
| **Org pools** | Team/Enterprise can attach seats to a shared balance (enterprise cost control) |
| **Metering** | Tokens, tool rounds, image/OCR/search units as applicable |

Businesses may buy **only** Credits, **only** platform seats, or both. Solo users should have no practical reason to subscribe unless they explicitly want hosted inference without managing keys.

---

## Explicitly out of scope for business freemium

Do **not** implement freemium by:

- Gating **existing** specialized toolsets, Calc/Draw tools, Python sandbox, vision, image gen, MCP, or personal embeddings behind a paid license  
- Breaking offline or BYO-key workflows for unpaid users  
- Requiring cloud login for basic chat send  
- Dual-licensing the entire extension as the *only* way to get today’s features  

If a future feature is both valuable and free-by-default for individuals, prefer shipping it free and selling **admin, multi-user, hosted, or vertical packaging** around it.

---

## Packaging matrix (business features only)

Rows are **new**. Existing free capabilities are omitted on purpose.

| New capability | Cloud Credits | Team | Business / Enterprise |
|----------------|:-------------:|:----:|:---------------------:|
| Hosted inference / usage meters | ● | ○ | ○ |
| Seats + org credit/key pool | | ● | ● |
| Admin defaults & approved OXT channel | | ● | ● |
| Shared prompt / style library | | ● | ● |
| Shared / ACL team RAG | | ● | ● |
| Light audit export | | ◐ | ● |
| Full policy matrix & egress control | | ◐ | ● |
| SSO / advanced identity | | | ● |
| Private gateway / residency | | | ● |
| Air-gap channel + license server for *platform* features | | | ● |
| Managed connector catalog | | ◐ | ● |
| Vertical packs | add-on | add-on | add-on / included set |
| SLA & success | | paid support | ● |

● included · ◐ limited subset · ○ optional attach · blank = not part of that SKU

---

## Pricing and packaging notes (non-binding)

| Motion | Suggestion |
|--------|------------|
| **Team** | Per seat / month, annual discount; minimum seat floor (e.g. 3–5) |
| **Enterprise** | Annual contract; seats + platform fee; overage for audit storage / RAG volume |
| **Cloud Credits** | Prepaid packs or monthly commit; org pool |
| **Vertical packs** | Flat add-on per org or per seat |
| **FOSS goodwill** | Public roadmap for free extension; business features documented as separate products |

Exact price points are out of scope for this doc.

---

## Architecture implications (high level)

Implementation detail will live in later design/PRs. Directionally:

1. **Entitlement applies only to new modules and cloud APIs**, not to the existing free tool registry’s core availability.  
2. **Unsigned / logged-out clients** behave as today’s free product.  
3. **Org policy** is enforced when:
   - the client is bound to an org session, and/or  
   - requests go through an org gateway that enforces allowlists server-side (preferred for security-critical rules).  
4. **Server-side enforcement** for credits, SSO, audit ingest, and team RAG; client-side flags only for UX (upsell entry points to *new* modules).  
5. **GPL boundary:** Prefer SaaS and separate commercial services/assets; avoid shipping a closed replacement for free core code. Asset packs and cloud APIs are clean boundaries.

No code paths in this document are required to exist yet.

---

## Go-to-market narrative

**For IT / security:**  
“Deploy the same free WriterAgent your users want. Add org keys, model and egress policy, audit, and private routing when you need control—without taking tools away.”

**For team leads:**  
“Share house style, a company knowledge base, and vertical playbooks so agents follow *our* process.”

**For finance:**  
“One credit pool and seat list instead of shadow API keys on every laptop.”

**For community / power users:**  
“Everything you already use stays free. Paid tiers are for IT and compliance at scale—SSO, audit, fleet policy—not ‘Pro AI’ features you would miss as a solo user.”

---

## Success metrics (when shipping)

| Metric | Why |
|--------|-----|
| Free MAU of extension (unchanged or up) | Confirms no accidental paywall of core |
| Team trial → paid conversion | Platform value |
| % of Team orgs attaching Cloud Credits | Orthogonal SKU health |
| Support tickets: “feature I used to have is locked” | Should stay ~0 |
| Enterprise: time-to-first-policy (SSO + allowlist) | Implementation quality of control plane |
| Net revenue retention on seats | Expansion via packs / credits |

---

## Phased delivery (suggested)

### Phase 0 — Product freeze on free surface

- Document and test: unpaid / logged-out = full current feature set  
- No entitlement checks on existing tools

### Phase 1 — Cloud Credits (optional)

- Hosted chat completions path; trial + packs  
- Org pool can wait for Phase 2

### Phase 2 — Team control plane MVP

- Seats, org keys or shared credits, admin default models  
- Shared prompt/style library sync  
- Soft upsell entry points only into **new** UI (e.g. “Team library”)

### Phase 3 — Team RAG + light audit

- Admin corpus + ACL basics  
- Exportable action log for cloud-mediated runs

### Phase 4 — Enterprise hard controls

- SSO, full policy matrix, private gateway, retention, SLA packaging  
- Air-gap channel as services engagement

### Phase 5 — Vertical packs

- First-party Legal/Sales/Finance packs calling free tools  
- Measure attach rate before marketplace

---

## Open decisions

| Decision | Options | Notes |
|----------|---------|--------|
| License key vs pure SaaS login | SaaS session only vs offline license for air-gap platform features | Offline orgs need a story that still leaves free tools free |
| Whether Team RAG shares code with personal embeddings | Shared indexer with multi-tenant host vs separate service | Prefer reuse of free indexer where safe |
| MCP: free forever vs free DIY + paid catalog | Catalog is paid; DIY MCP stays free | Matches “no regression” rule |
| Marketplace for third-party packs | Later | Legal (GPL, trademarks, liability) first |
| Brand name for platform | “WriterAgent for Teams / Business” | Keep “WriterAgent” = free extension |

---

## Related docs

| Doc | Relevance |
|-----|-----------|
| [AGENTS.md](../AGENTS.md) | Product surface and architecture entry points |
| [docs/embeddings.md](embeddings.md) | Personal embeddings/FTS (stays free; team RAG is additive) |
| [docs/mcp-protocol.md](mcp-protocol.md) | MCP (DIY free; managed catalog is freemium) |
| [docs/ppt-master-integration-plan.md](ppt-master-integration-plan.md) | Deck generation primitives for Sales packs |
| [docs/writer-reviewable-agent-edits.md](writer-reviewable-agent-edits.md) | Free single-user review; co-review is future paid collab |
| [docs/ROADMAP.md](ROADMAP.md) | Engineering roadmap (this doc is commercial/product) |

---

## Summary

Business freemium for WriterAgent should **add enterprise-only layers** that normal users would not want or need:

1. **Org control plane** (seats, keys, defaults)  
2. **Team knowledge and shared style/prompt libraries** (multi-user, admin-governed)  
3. **Policy, audit, SSO, private gateway** for Enterprise  
4. **Vertical workflow packs and support SLAs** (org rollout, not solo shortcuts)  
5. **Optional Cloud Credits** (hosted inference convenience—orthogonal to the enterprise story)  

It should **not** remove or rent-seek on the existing free agent in LibreOffice, and it should **not** sell individuals “better AI.” That separation is the product contract with users and the cleanest fit for a GPLv3+ extension plus commercial services.
