# Labeling Guidelines — Support-Ticket Triage v1

Read this before writing a single label. The rubric's job is that **two
careful labelers agree ≥ 90%** of the time; anything they'd fight about
belongs in the hard-case catalogue (§6), not in ad-hoc judgment.

---

## 1. Redaction first (non-negotiable)

Before labeling, redact the text. Never label raw tickets.

| Replace | With |
|---|---|
| person names | `[PERSON]` |
| email addresses | `[EMAIL]` |
| phone numbers | `[PHONE]` |
| order / invoice numbers (real ones) | `[ORDER]` |
| card / IBAN / account digits | `[CARD]` |
| URLs with tokens/ids | domain only, e.g. `status.example.com` |

Keep sentence structure — `[PERSON] was billed twice for [ORDER]` labels the
same as the original. Real-looking but fictional IDs (e.g. `INV-2026-0117`)
may stay; **real** identifiers never do. If a ticket cannot be redacted
without losing the label signal, drop the ticket and take a replacement.

---

## 2. The three labels

### 2.1 `department` — exactly one of `billing / technical / sales / account`

Ask: *which single team should own this ticket first?* First team, not every
team — a billing bug fixed by technical support is still **billing** if the
customer's actual complaint is about money.

```text
Is the customer's primary complaint about money? (charged, refunded,
overbilled, invoice, subscription price, payment failed)
├─ yes → but the money issue was caused by a technical failure the customer
│         describes in detail (duplicate charge from a retry bug)?
│         └─ still money-primary → BILLING        (hard case H1)
├─ yes, otherwise → BILLING
└─ no
   Is it about their account state? (login, password, 2FA, profile,
   permissions, data/deletion, subscription STATUS questions)
   ├─ yes → ACCOUNT
   └─ no
      Do they want to buy, upgrade, or ask pre-purchase pricing?
      ├─ yes → SALES
      └─ no
         Is it about something broken or not working? (bug, crash,
         outage, sync, error message, integration)
         ├─ yes → TECHNICAL
         └─ no → flag `confident: false`; bring to QC
```

**Tie-break (must be recorded in `meta.notes`):**
- Money complaint + wants a product change to fix it → BILLING.
- "Cannot log in to pay my invoice" → ACCOUNT (the blocking state is
  account access; the invoice is context).
- Cancellation requests → ACCOUNT (subscription status), unless the stated
  reason is "I was overcharged and want out" → BILLING.

### 2.2 `urgency` — expected rubric level 0/1/2

Score what the **text asserts**, not what you infer about the customer's
business. 0 = not urgent, 1 = soon, 2 = critical.

```text
Does the text assert any of:
  - money actively blocked/frozen, or security incident, or
    total inability to use a paid product?
├─ yes → 2 (critical)
└─ no
   Does it assert degraded workflow, a deadline, or explicit
   time pressure ("since yesterday", "need it this week")?
   ├─ yes → 1 (soon)
   └─ no → 0 (not urgent)
```

Signals table:

| Level | Asserted signals |
|---|---|
| 2 | "account locked", "cannot access paid service at all", "payments failing for all customers", "data loss", "security breach" |
| 1 | "since yesterday", "deadline Friday", "blocks one workflow", "several users affected", "still waiting" |
| 0 | questions, feature requests, how-tos, mild annoyance, no time claim |

- Duration ("for two weeks") alone never promotes 0→1; pair it with an
  asserted impact ("still blocked for two weeks" → 1, "can't work at all" → 2).
- Politeness and exclamation marks are NOT urgency.
- A refund request never changes urgency by itself.

### 2.3 `refund` — boolean

True iff the customer **asks for money back**: refund, money back,
reimbursement, "reverse the charge", "cancel and refund".

| Statement | `refund` |
|---|---|
| "Please refund the duplicate charge." | true |
| "I want my money back for November." | true |
| "Can I exchange this for the Pro plan?" | **false** (exchange ≠ refund) |
| "Please issue a credit note." | **false** (store credit ≠ money back) |
| "Cancel my subscription." (no money-back ask) | **false** |
| "I disput[ed] the charge with my bank." | true — a chargeback is a money-back demand |
| "What is your refund policy?" | **false** (question, not a request) |

---

## 3. Composition targets (repeated from README; validator enforces)

Per 50: billing 15 / technical 15 / sales 8 / account 12 · urgency 20/18/12 ·
refund true 15 (incl. 2 "money-adjacent but false" traps) · 6 non-en ·
≥ 8 hard cases.

---

## 4. Multilingual tickets (the 6 non-en slots)

Write them natively (not translated English) for one of: es, de, fr, zh.
Set `language` accordingly. Same rubric. These exist to exercise the Router
and language-evidence logging (blueprint §8 item 10), so make 2 of them
**subtle**: e.g. German with an English product name, or a French ticket
that starts with an English greeting.

---

## 5. QC and disagreement handling

1. Labeler writes ticket + labels + `confident` flag + `labeler` id.
2. Every `confident: false` record gets a second labeler; so does a random
   20% sample of the rest.
3. On disagreement: discuss, apply §2 decision trees, and set the
   **reconciled** label. Mark `disagreement: true` and keep both labeler ids.
4. If no rubric reading supports either label, the ticket is replaced, not
   force-labeled.

---

## 6. Hard-case catalogue (≥ 8 of the 50 must hit these; tag `meta.hard_case`)

| ID | Case | Correct labels | Why it's hard |
|---|---|---|---|
| H1 | Money complaint caused by a described technical bug | billing, any, true/false | bug detail pulls toward technical |
| H2 | "Cannot log in to pay my invoice" | account, 1, false | invoice context pulls toward billing |
| H3 | Chargeback mentioned | any, 1, **true** | no word "refund", but money-back demand |
| H4 | Store credit / credit note requested | billing, 0, **false** | money words but not money-back |
| H5 | Multi-team ticket (billing + technical detail) | billing-first, any, — | split-attention |
| H6 | Urgent-sounding but level 0 ("ASAP!!" on a how-to question) | any, **0**, — | tone ≠ urgency |
| H7 | Long-running but low impact ("feature request pending 2 years") | sales/account, 0, — | duration ≠ urgency |
| H8 | Question about refund policy (no request) | any, 0, **false** | word "refund" without the ask |
| H9 | German/French ticket with English product name | correct dept, any, — | language-routing subtlety |
| H10 | Cancellation because of overcharge | billing, 1, false unless money-back ask | cancellation vs refund conflation |

---

## 7. Prohibited content

No real PII (§1). No abusive content, no medical/legal/financial advice
scenarios, no real company or product names — invent plausible ones
(`status.example.com`, "CloudSync Pro"). Tickets must be ≥ 20 and ≤ 2000
chars (schema-enforced).
