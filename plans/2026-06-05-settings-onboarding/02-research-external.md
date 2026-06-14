<!-- GENERATED — edit .claude/skills/groundwork/ instead. Synced by sync-from-dev.mjs. -->
# 02 — External research

Outside research backing Add a settings mechanism plus onboarding that captures display name and usage type (business/personal) so welcomes are personalized and business users can record business info; decide whether settings live on an authenticated web page or via WhatsApp commands.. Cite every claim with a URL + access date. Hand-authored sections live between fences; the research action only writes inside.

## Findings

<!-- groundwork:auto:start findings -->
<!-- last_action: research · 2026-06-05T10:56:03Z -->
## 1. In-chat settings vs. companion web page

Real WhatsApp Business / chatbot products increasingly keep configuration and data capture *inside* the chat using the Cloud API's native interactive primitives (reply buttons, list messages, and the newer WhatsApp Flows) rather than bouncing users to a web page — chiefly to remove context-switching friction and avoid a second authentication surface. The Cloud API offers three relevant interactive message types for lightweight settings menus, each with hard limits that shape what a chat-based settings UX can do.[^1][^2][^3]

- Interactive **reply buttons** cap at **3 buttons** per message (each with a unique ID for backend routing); **list messages** allow up to **10 sections / 10 rows total**, section title ≤24 chars, row title ≤24 chars, row description ≤72 chars.[^2][^3]
- Reply-button and list messages are **NOT templates** and require **no pre-approval** — they can be sent freely within the 24h customer-service window.[^1][^2]
- Richer-than-a-menu capture (multi-field forms) needs either **Flows** or a web page; on **WhatsApp Web/desktop, Flows do not render interactively** (users are told to finish on mobile) — a real constraint for desktop users.[^3][^5][^6]
- Vendor-cited Flows vs. external-web-form: ~60–90s vs 5–10 min completion, ~12% vs ~35% abandonment (directional, vendor-reported).[^4]

## 2. WhatsApp Flows — native in-chat forms

WhatsApp Flows are Meta's native, full-screen, multi-screen form experience that opens *inside* the chat (no website redirect), purpose-built for structured capture like onboarding and lead intake — a direct fit for a name + usage-type + business-profile onboarding flow. They carry a publish/review step and desktop limitations.[^4][^5][^6][^7]

- Input components include **text input** (with email/phone/number validation), **dropdown** (~200 options), **radio buttons**, **checkbox/multi-select** (returns an array), **date picker**, **opt-in**, **star rating**; a Form component disables the footer CTA until required fields are complete.[^5][^6][^8]
- A Flow **must be published and passes a Meta review** (vendors describe approval as typically same-day) — not as frictionless to ship as ad-hoc button/list messages.[^5][^7]
- Flows run in **every market the Cloud API serves (200+ countries)** including Nigeria, on recent Android/iOS WhatsApp; **desktop/Web does not render them interactively**.[^4][^6]
- A Flow opened within the 24h service window (user messaged first) is free/low-cost service or utility messaging, not premium marketing.[^9][^10]

## 3. Onboarding data minimization & conversational onboarding

The consistent evidence: **fewer upfront fields raise completion**, and **progressive profiling** (collect the minimum to deliver value, enrich later) plus one-question-at-a-time *conversational* presentation both lift completion/activation — strongly supporting asking only display name + usage type first and deferring business detail.[^11][^12][^13]

- HubSpot (40,000+ landing pages): ~3 fields converted ~25%, dropping to roughly half by ~8 fields; multiple dropdowns and textareas specifically depress conversion.[^13]
- Imagescape case: conversions rose **120%** after cutting a form from **11 → 4 fields**.[^11]
- Progressive profiling cited with conversion lifts up to ~20%; role/use-case-based flows (e.g. business vs personal) cited lifting activation 30–50%.[^11][^12]
- Conversational, one-question-per-screen presentation cited ~15–25% higher completion than all-fields-on-one-page.[^11]

## 4. Personalization — using the person's name

Using a person's name in greetings is a low-cost lever with repeatedly measured engagement gains in email (the closest well-studied analog to a WhatsApp greeting), supporting capturing a display name primarily to personalize welcomes.[^14][^15]

- First-name personalization cited increasing opens ~26%, CTR ~10.6%.[^14]
- Experian-attributed study: personalized emails had **29% higher unique opens**, **41% higher unique clicks**; personalized subject lines cited lifting opens ~50%.[^14][^15]
- Caveat: email-channel, largely vendor-reported — treat magnitudes as directional, not WhatsApp-specific.[^14][^15]

## 5. Business vs personal modeling & minimal business fields

Fintech/accounting products let users self-select a context, then collect a deliberately small business profile; across QuickBooks and Wave the recurring minimal fields are **business name, business type/industry, country, and currency** — a useful template for what a bookkeeping product minimally needs to localize ledgers and personalize.[^16][^17]

- **Wave** collects **country** and **business currency** up front, plus editable name/address/contact.[^16][^17]
- **QuickBooks** asks **business type/industry** (customizes dashboard + chart of accounts) and stores company name/address/contact; multi-currency is an opt-in advanced setting, not a default onboarding field.[^17]
- Minimal useful bookkeeping fields: **legal/display business name, business type/category, currency** as core; tax/registration IDs optional and deferrable.[^16][^17]
- WhatsApp pricing context: from **1 July 2025**, per-message pricing by category (service/customer-initiated within 24h **free**; utility templates within the service window **free**) — onboarding triggered by the user's own inbound message is low/zero marginal cost.[^9][^10]

## 6. Nigeria / African SME-specific considerations

For Nigeria-first SMEs the dominant reality is informality: most micro/small businesses are unregistered with no tax identity, so onboarding **must not assume a registration number** and should keep business fields optional and low-friction, while being mindful that financial data is sensitive.[^18][^19]

- **>60% of MSMEs operate without CAC registration or a tax identity** — a registration/RC number cannot be a required field.[^18]
- Formalization is being lowered (SMEDAN–CAC free-registration drive; fintechs like Kippa registering informal businesses in ~72h), but the baseline should remain unregistered/informal.[^18][^19]
- Digital bookkeeping is itself framed as the new credit/credibility signal — reinforcing low-friction capture so users actually keep records, implying the business profile should be optional enrichment, not a gate.[^18]
- Field-design implication: lean on display name + category; treat legal business name / registration as optional; minimize sensitive data up front.[^18][^19]
<!-- groundwork:auto:end findings -->

## How to use this file

Hand-written context — what you specifically went looking for and why. The research action does not touch this section. Keep it terse; the findings above are the substance.

## Sources

<!-- groundwork:auto:start sources -->
<!-- last_action: research · 2026-06-05T10:56:03Z -->
1. Sending Interactive Messages — Meta for Developers — https://developers.facebook.com/docs/whatsapp/guides/interactive-messages/ (accessed 2026-06-05)
2. Interactive Reply Buttons — WhatsApp Cloud API (Meta) — https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-reply-buttons-messages/ (accessed 2026-06-05)
3. Interactive List Messages — WhatsApp Cloud API (Meta) — https://developers.facebook.com/docs/whatsapp/cloud-api/messages/interactive-list-messages/ (accessed 2026-06-05)
4. WhatsApp Flows: Capture Data With Native WhatsApp Forms — WANotifier — https://wanotifier.com/whatsapp-flows/ (accessed 2026-06-05)
5. WhatsApp Flows Guide 2025 — wa.expert — https://wa.expert/pages/whatsapp-flows-guide (accessed 2026-06-05)
6. WhatsApp Flows — Meta for Developers — https://developers.facebook.com/docs/whatsapp/flows/ (accessed 2026-06-05)
7. Components — WhatsApp Flows — Meta for Developers — https://developers.facebook.com/docs/whatsapp/flows/reference/components/ (accessed 2026-06-05)
8. Flows | Client Documentation — 360dialog — https://docs.360dialog.com/docs/messaging/flows (accessed 2026-06-05)
9. WhatsApp Messaging Pricing — Twilio — https://www.twilio.com/en-us/whatsapp/pricing (accessed 2026-06-05)
10. Meta WhatsApp Pricing 2026 — go4whatsup — https://www.go4whatsup.com/guides/meta-whatsapp-pricing/ (accessed 2026-06-05)
11. 10 Customer Onboarding Best Practices to Boost Completion Rates in 2025 — Formbot — https://tryformbot.com/blog/customer-onboarding-best-practices (accessed 2026-06-05)
12. Progressive Profiling for Frictionless Onboarding — SSOJet — https://ssojet.com/ciam-qna/progressive-profiling-frictionless-onboarding (accessed 2026-06-05)
13. Which Types of Form Fields Lower Landing Page Conversions? — HubSpot — https://blog.hubspot.com/blog/tabid/6307/bid/6746/which-types-of-form-fields-lower-landing-page-conversions.aspx (accessed 2026-06-05)
14. The Impact of Personalization on Email Open Rates — Air Traffic Control — https://www.airtrafficcontrol.io/en/blog/the-impact-of-personalization-on-email-open-rates-a-deep-dive (accessed 2026-06-05)
15. Study: Personalized email subject lines increase open rates by 50% — Marketing Dive — https://www.marketingdive.com/news/study-personalized-email-subject-lines-increase-open-rates-by-50/504714/ (accessed 2026-06-05)
16. Add a new business to your Wave account — Wave Help Center — https://support.waveapps.com/hc/en-us/articles/208624306 (accessed 2026-06-05)
17. Edit company settings — QuickBooks Online (Intuit) — https://quickbooks.intuit.com/learn-support/en-us/help-article/update-products/edit-company-settings-quickbooks-online/L6cZwzGez_US_en_US (accessed 2026-06-05)
18. How Small Informal MSMEs Can Prove Creditworthiness Without Collateral in Nigeria 2025 — Biznalytiq — https://biznalytiq.com/2025/11/02/how-small-informal-msmes-can-prove-creditworthiness-without-collateral-in-nigeria-2025/ (accessed 2026-06-05)
19. Accounting App Kippa Launches Second Product for Extended SME Payments in Nigeria — The Fintech Times — https://thefintechtimes.com/accounting-app-kippa-launches-second-product-for-extended-sme-payments-in-nigeria/ (accessed 2026-06-05)

> **Caveat (researcher note):** Several Flows component-level limits (e.g. ~200 dropdown options, "same-day" review) and the personalization/form-field stats are vendor- or email-channel-sourced and should be reconfirmed against primary Meta docs and original studies before being load-bearing. No WhatsApp-specific controlled study on name personalization was found.
<!-- groundwork:auto:end sources -->
