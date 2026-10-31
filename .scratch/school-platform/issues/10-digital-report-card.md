# What does the digital report card (học bạ số) require of a school system from 2027?

Type: research
Status: resolved
Blocked by:

## Question

Circular 89/2026/TT-BGDĐT (effective 1 Dec 2026, per `docs/research/assessment-regulations.md`) introduces a digital report card. What must a school management system do to produce one: data fields and format, digital signatures (who signs, which certificate providers), storage and retention, hand-off between Schools on transfer, any national platform it must be submitted to, and the deadline by Level and Grade? Is a printable PDF still accepted, and until when? Answer decides whether the digital report card belongs in the MVP.

## Answer

Findings: branch `research/digital-report-card`, file `docs/research/digital-report-card.md` (not legal advice). Circular 70/2026, its 8 Oct 2026 effective date and its main articles were spot-checked by the main session against secondary legal press (lsvn.vn, hcc.nghean.gov.vn, hoatieu.vn).

- **Circular 70/2026/TT-BGDĐT** (signed 22 Aug 2026, in force **8 Oct 2026**) governs the digital report card. Circular 89/2026 only points to it. Every general-education School must create one for current and new students from 8 Oct 2026, with no phasing by Level. The earlier assessment research missed this circular.
- Signing in two layers: personal digital signatures (subject teacher, then homeroom teacher, then principal or a delegate), then the School's organisational signature. Once issued, a record is locked; a correction means revoke and re-issue.
- Records sync to the National Database on Education and Training and can be looked up on VNeID and the National Public Service Portal. On transfer, data goes to the receiving School with the student's consent. Receivers may not ask for a paper copy of a valid digital one. Paper records made before 8 Oct 2026 stay valid.
- Technical spec (fields, XML, signature providers VNPT/BKAV/Viettel/Cipher Committee, a six-call API) is only in Decision 3016/QĐ-BGDĐT (2025), seen through a mirror that says it expired 1 Sep 2026, with no successor found. Vendors must get the current spec from MOET or a provincial Department.
- Recommendation: a scoped slice in the MVP. That means a per-year record model, the sign-off chain with audit trail, XML + PDF output, a hook for an external signing provider, and transfer between Schools. Live submission to MOET, VNeID lookup, revocation and digitising old paper records wait for the official spec and a MOET account.
