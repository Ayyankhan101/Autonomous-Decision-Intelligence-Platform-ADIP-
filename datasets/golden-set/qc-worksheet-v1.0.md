# Golden v1.0 Human QC Worksheet (AI-3 sweep assistant)

Records: 50. The AI-3 sweep below is evidence-based, not a human pass.
For each flagged row: read the ticket + guidelines section 2, then fill in the decision.
**Any amended label = new dataset version (v1.1) per the freeze discipline.**

## Must-flag (0) — label seems unsupported by text evidence

- (none)

## Verify (12) — evidence ambiguous, confirm current label

- [ ] TICKET-0011: department=technical has no lexical signal in text (tie-break case?)
  - labels: dept=technical urg=0 refund=False | lang=es
  - text: "La app móvil olvida mis filtros guardados cada vez que la cierro. No es urgente, pero parece un fallo: los ajustes deberían conservarse entre sesiones."
- [ ] TICKET-0015: department=account has no lexical signal in text (tie-break case?)
  - labels: dept=account urg=0 refund=False | lang=de
  - text: "Wir möchten die Workspace-Verwaltung an einen zweiten Admin übergeben, da ich im Herbst aussteige. Unterstützt CloudSync Pro die Übertragung der Eigentümerrolle direkt in der Konsole?"
- [ ] TICKET-0018: department=account has no lexical signal in text (tie-break case?)
  - labels: dept=account urg=0 refund=False | lang=zh
  - text: "我们已把所有资料迁移到新工作区，请删除旧工作区的数据，并在清理完成后发送确认。谢谢。"
- [ ] TICKET-0021: department=technical has no lexical signal in text (tie-break case?)
  - labels: dept=technical urg=2 refund=True | lang=en
  - text: "Since this morning every shared link returns access denied for external partners and nothing can be sent to clients — deliverables due tomorrow cannot go out at all. Please also refund this month's fee; the product is completely unusable for us today."
- [ ] TICKET-0022: department=sales has no lexical signal in text (tie-break case?)
  - labels: dept=sales urg=0 refund=False | lang=en
  - text: "We first asked about an enterprise tier with on-prem sync two years ago. Is that still on the roadmap? We're comfortable on Standard — just checking in."
- [ ] TICKET-0024: department=billing has no lexical signal in text (tie-break case?)
  - labels: dept=billing urg=0 refund=False | lang=en
  - text: "If we cancel our annual plan mid-term next year, how are refunds for unused months handled? No issue right now — we just want the policy in writing for our procurement file."
- [ ] TICKET-0025: department=technical has no lexical signal in text (tie-break case?)
  - labels: dept=technical urg=0 refund=False | lang=en
  - text: "The beta dark-mode toggle sometimes resets to light mode after a restart. Cosmetic only, no workflow impact, but noting it for the fix list."
- [ ] TICKET-0029: department=account has no lexical signal in text (tie-break case?)
  - labels: dept=account urg=0 refund=False | lang=fr
  - text: "Hello team, je souhaite renommer l'espace de travail avec le nom de notre nouvelle filiale et changer le contact de facturation. Quelles sont les étapes à suivre ?"
- [ ] TICKET-0032: department=technical has no lexical signal in text (tie-break case?)
  - labels: dept=technical urg=0 refund=False | lang=de
  - text: "Die Tastenkombination zum Einklappen von Unterhaltungen funktioniert auf Windows 11 nicht, obwohl sie in der Doku steht. Kleinigkeit, aber die Tabelle sollte stimmen."
- [ ] TICKET-0037: department=account has no lexical signal in text (tie-break case?)
  - labels: dept=account urg=0 refund=False | lang=en
  - text: "Can two-factor authentication be enforced as a default policy for every member of our workspace instead of per-user opt-in?"
- [ ] TICKET-0043: department=technical has no lexical signal in text (tie-break case?)
  - labels: dept=technical urg=0 refund=False | lang=en
  - text: "ASAP!! How do I switch my notifications to the daily digest? I keep getting pinged every few minutes and it's driving me nuts. This is really urgent!!"
- [ ] TICKET-0049: department=technical has no lexical signal in text (tie-break case?)
  - labels: dept=technical urg=1 refund=False | lang=en
  - text: "Since yesterday's username migration the iPad app shows invalid workspace on sign-in while desktop and web work fine. I travel today and need mobile access working."

## Sign-off

| Field | Value |
|---|---|
| Reviewer (human) | ____________ |
| Date | ____________ |
| Must-flags resolved | ____ / 0 |
| Verify-items resolved | ____ / 12 |
| Labels amended | ____ (0 => v1.0 stands; >0 => cut v1.1 with changelog) |
| Result | [ ] v1.0 CONFIRMED   [ ] v1.1 REQUIRED |
