# Digital report card (Học bạ số): what a school system must do from 2027

Ticket: `.scratch/school-platform/issues/10-digital-report-card.md`
Research date: 2026-10-31. Not legal advice. Have Vietnamese counsel confirm before launch.
Context: `docs/research/assessment-regulations.md` (branch `research/assessment-regulations`) covers Circular 89/2026; this note covers the rules that circular points to.

## 1. Bottom line

- The rules for the digital report card are in a separate circular the earlier research did not find: **Circular 70/2026/TT-BGDĐT** (signed 22 Aug 2026, effective **8 Oct 2026**). I read the signed PDF in full (section 2).
- Circular 89/2026 (effective 1 Dec 2026 per the Government portal) makes the digital report card part of the legally required assessment file and defers every detail to Circular 70.
- Field list, XML format and the vendor-to-Ministry API are **not** in either circular. They sit in a Ministry technical decision (Decision 3016/QĐ-BGDĐT, 31 Oct 2025). I could only read it through a mirror, and the mirror says it **expires 1 Sep 2026**. Whether a successor exists is **not verified**. Vendors need the official text and current version from the Ministry or a provincial Department.
- No rollout by Level and Grade exists in the texts I read. Circular 70 applies to all general-education Schools (Primary, Lower Secondary, Upper Secondary) from 8 Oct 2026 for current and new students, with a transition clause but no end date for paper.
- Recommendation: **yes, a scoped slice belongs in the MVP** (section 10).

## 2. Primary sources read

| Short name | Document | Source | How read |
|---|---|---|---|
| TT 70/2026 | Circular 70/2026/TT-BGDĐT, 22 Aug 2026, on managing and using học bạ số in general and continuing education | PDF on the Government portal: https://xdcs.cdnchinhphu.vn/446259493575335936/2026/8/26/70-bgddt-signed-1787729952462772151826.pdf . Also listed on MOET: https://moet.gov.vn/van-ban/van-ban-quy-pham-phap-luat/thong-tu-quy-dinh-ve-quan-ly-va-su-dung-hoc-ba-so-trong-cac-co-so-giao-duc-pho-thong-va-co-so-giao-duc-thuong-xuyen.html | Scanned image, OCR (macOS Vision). 12 pages read in full. Article numbers and key wording read cleanly; check any figure you hard-code against the PDF. |
| TT 89/2026 | Circular 89/2026/TT-BGDĐT, 16 Oct 2026 | https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/10/89-bgddt.signed.pdf ; metadata https://vanban.chinhphu.vn/?docid=220070&pageid=27160 | OCR. Effective date: portal metadata says 01/12/2026. The PDF has a handwritten day and month ("01" and a hand-written number that looks like "12" or "10"), so I rely on the portal. |
| KH 213/2024 | MOET Plan 213/KH-BGDĐT, 1 Mar 2024, pilot of học bạ số at Primary | https://caselaw.vn/van-ban-phap-luat/495509-ke-hoach-so-213-kh-bgddt-ngay-01-03-2024-cua-bo-giao-duc-va-dao-tao-trien-khai-thi-diem-hoc-ba-so-cap-tieu-hoc | **Mirror**, not MOET. Appendix partly behind login. |
| QĐ 3016/2025 | Decision 3016/QĐ-BGDĐT, 31 Oct 2025, data-format standard for học bạ số | https://luatvietnam.vn/giao-duc/quyet-dinh-3016-qd-bgddt-2025-chuan-hoa-dinh-dang-du-lieu-hoc-ba-so-440230-d1.html | **Mirror**, read through a fetch summary. Original PDF behind login. Not checked against the original. |
| CV 2239/2026 | Official Letter 2239/BGDĐT-KHCNTT, 29 Apr 2026, connecting and syncing học bạ số data | https://luatvietnam.vn/giao-duc/cong-van-2239-bgddt-khcntt-2026-huong-dan-ket-noi-dong-bo-du-lieu-hoc-ba-so-434141-d6.html | **Mirror**, summary only. Appendix scan partly garbled. |
| QN 442/2026 | Quảng Ngãi Department of Education letter 442/SGDĐT-GDTrH, 2 Feb 2026, implementing Official Letter 7802/BGDĐT-GDPT (27 Nov 2025) | https://tunghia.quangngai.gov.vn/upload/2006780/20260715/HUONGDANTRIENKHAIHBS_20252026.pdf | Provincial government PDF, OCR, 3 pages. A **provincial** document that cites the Ministry letter; I could not find Official Letter 7802 itself. |

thuvienphapluat.vn and luatvietnam.vn may block automated fetches. I used luatvietnam.vn only for the two Ministry texts above, and only as a mirror.

## 3. Data fields and format

What the primary texts say (TT 70 Arts. 3, 6, 7, 14):
- Học bạ số is "electronic data recording, in a systematic way, the learner's learning process, results, conduct, comments and related information" (Art. 3.1).
- The field list, field structure, format, display rules and encoding rules are **set by MOET separately** (Art. 6.1, 6.2). The standard must be nationwide, use an **open format**, connect to the National Database on Education and Training, and support lookup, authentication, extraction and long-term storage (Art. 6.3).
- One học bạ số per learner, tied to the learner's **lifelong learning record number** (Art. 7.1). Created per school year, by **30 June** each year; special cases get a later date (the OCR of the second date is incomplete) (Art. 7.4).
- Content comes from the School's own records, identity data and education-management data (Art. 7.3). For TT 89, the "fields and assessment content on the template" of the TT 22 Annex Học bạ are the professional content (TT 89 Art. 22). Paper-only rules (pen colour, red-ink corrections, seals, hand-over) apply to paper only.
- A unified, unique identifier is required at the connection layer (Art. 14.3.b).

What Decision 3016/2025 says, **via the mirror only** (not verified at source):
- Stored as **XML**, UTF-8, tag names without diacritics, null values omit the tag. Dates `dd/MM/yyyy`; signing times ISO 8601; up to 4 decimal places.
- Report card ID: **UUID v4**, generated by school software, one per issued card, never reused after revocation.
- Structure: `HOC_BA` root with `DU_LIEU_HOC_BA` (general info, learning history for transfers, summary), a signature list (homeroom teacher `GVCN`; subject teachers `GVBM` for secondary), and an issuance block (principal `CBQL` plus a School-level signature).
- Fields: school year, School and Department codes, Level code, student name, 12-digit citizen ID, student code, gender, date of birth, addresses, ethnicity, disability flag, parents or guardians; per-subject scores and comments; qualities and competencies; overall result; awards; promotion flag.
- Separate appendices for Primary and for Lower/Upper Secondary and continuing education, with code catalogues and display templates.
- CV 2239/2026 (mirror summary) adds fields to the general-info group: `MA_DDTC` (organisation identifier), `MA_XA_PHUONG` (ward code) and `MA_TINH_THANH_PHO` (province code). It also says students with no personal ID number need case-by-case handling, and foreign students register an electronic ID account under Decree 69/2024/NĐ-CP.

Gap: I did not see the exact field list or XSD. A vendor cannot build this from my notes.

## 4. Digital signatures

From TT 70 Arts. 3.5, 8, 9 (read directly):
- **Two signing layers**: a personal digital signature of the person with authority, and an **organisational** digital signature of the School (Art. 3.5, 8.1, 9.2).
- Who signs (Art. 9.1): the subject teacher, the teacher in charge of an educational activity, the homeroom teacher, the head of the School, or a person assigned or authorised under law.
- Order (Art. 9.3): complete data, check and confirm, personal signature, School signature, update the signing status in the system. Signing is **per school year** (Art. 9.4).
- TT 89 Art. 9 (Primary) fixes the order: each subject teacher signs their own subject on the học bạ số, then the homeroom teacher signs the class record.
- Issue only after validation and valid signing (Art. 8.2). After issue, no direct editing; a changed record needs revoke and re-create, or re-validate, re-sign and re-issue (Art. 7.5, 10.3).
- Each issue of the record, its electronic copy or extract is logged: time, issuer, purpose, recipient (Art. 10.2).
- Signatures must carry legal value and be verifiable (Art. 8.4). The legal base listed in the preamble includes Decree 23/2025/NĐ-CP on electronic signatures and trust services.

Certificate providers and types (**not in the circulars**):
- Decision 3016 via the mirror: qualified e-signature; certificate types `REMOTE_SIGNING` and `USB TOKEN`; providers listed `VNPT`, `BKAV`, `VIETTEL`, `BAN_CO_YEU` (Government Cipher Committee). The School registers its organisational certificate and its provincial Department approves it; only approved certificates can sign. School software must verify the certificate and warn before expiry. Cited signature-format circulars: 39/2017 and 22/2020 (not verified against the original).
- Plan 213/2024 (mirror) references Decree 130/2018/NĐ-CP and a centralised signing service from the Government Cipher Committee for the pilot, and says the Department chooses the signing solution.
- Quảng Ngãi 442/2026 tells Schools to equip staff with certificates under Decree 68/2024/NĐ-CP (special-purpose public-sector signatures), coordinated through the Government Cipher Committee. That decree is for the state sector. Whether **private** Schools use commercial certificates (VNPT, BKAV, Viettel) or the same channel I could not verify. Ask a provincial Department.

## 5. Storage and retention

TT 70 Arts. 16, 17, 22 (read directly):
- Data must be stored safely, completely and continuously, searchable and verifiable throughout the learner's studies **and after they leave** (Art. 16.1).
- **Retention period** follows archive law and other rules (Art. 16.2). TT 70 gives no number. The archive-law period is not verified here.
- Must have: integrity, authenticity, availability, backup and restore, an audit trail of create, update, edit, access and share, and edits stored with change history (Art. 16.3, 16.5).
- Schools and education authorities back up periodically and test restore (Art. 16.4). Storage must stay synced to the National Database on Education and Training (Art. 16.6).
- Security: access control by role, protect accounts and signing keys, incident reporting; forbidden acts include forging signatures (Art. 17).
- The learner may request correction. The School must process it within **10 working days** of a valid file (Art. 22.8). The School is accountable for data accuracy (Art. 22.9).
- A vendor (technology solution provider) must meet technical, security and confidentiality requirements by contract and law (Art. 23.3). Whether Vietnamese data-residency rules apply to a SaaS vendor is not covered here (not verified).

## 6. Transfer between Schools

- Data are acquired from sources including "data synchronised or forwarded from another education institution when a learner transfers" (TT 70 Art. 13.1.c). The receiving School must receive, reconcile, update and sync, to keep learning continuous (Art. 13.3). Records are "inherited" on transfer (Art. 7.6).
- Sharing between Schools and authorities needs authority, purpose, authentication, access control, a sharing history, and the data subject's **valid consent** unless law says otherwise (Art. 15).
- Primary to Lower Secondary hand-over is a data hand-over between the School and the local education authority, with no re-testing (TT 89 Art. 6, replacing TT 27 Art. 12.2.b). The Department supervises inheritance, transfer and sync of học bạ số on change of class, Level or School (TT 89 Art. 6, new Art. 12.3).
- The mechanism (pull from the national database, or School-to-School push) is **not specified** in the circulars. MOET's technical document defines it (Art. 14.4).

## 7. National platform and submission

- TT 70 Art. 14: School data **must connect and sync** with the **National Database on Education and Training**, by MOET's data and technical standards. It must also be usable on the **National Education Digital Platform**, the **National Public Service Portal** and **VNeID**.
- Learners and parents look up the record via school software, the National Public Service Portal and VNeID, where connection conditions are met (Art. 11.2).
- Minimum connection requirements (Art. 14.3): open format, unique identifier, authentication and access control, audit and status checks, secure transfer, real-time or periodic sync.
- Receiving agencies must not demand extra paper if the digital record qualifies (Art. 12.3). Where their system cannot connect online, an authenticated electronic copy or extract works (Art. 12.4, 25.3).
- A learner may ask the School to convert the record to paper; it is **free** (Art. 12.5).
- Per CV 2239/2026 (mirror): Schools connect with an account on the "database on Early Childhood, General, and Continuing Education"; a School without an account gets one through its provincial Department, which asks MOET.
- Per Decision 3016 via the mirror: six API transactions (submit, query result, register certificate, query certificate result, submit revocation, query revocation). Payload is the XML, gzip-compressed, Base64-encoded, with an authentication object (token, username, hashed password, unit code, school year). Not verified.
- MOET runs a "Kho học bạ số" (digital report card store) at national level; the pilot reported 4,241,906 Primary records from 59 Departments by mid-2024 (press, https://giaoduc.net.vn/ha-noi-dan-dau-toan-quoc-ve-ket-qua-thi-diem-hoc-ba-so-cap-tieu-hoc-post244746.gd , via search snippet only).

## 8. Rollout, deadlines, and the paper PDF question

| Item | What the texts say | Source |
|---|---|---|
| TT 70 effective | 8 Oct 2026 | TT 70 Art. 24 |
| Create học bạ số for current and new students | From 8 Oct 2026, all general-education and continuing-education Schools (Primary, Lower Secondary, Upper Secondary). No Level or Grade phasing in the text | TT 70 Art. 25.2 |
| Legacy paper records | Digitisation, standardisation and updating follow a **roadmap issued by MOET**, priority to current students. I did not find the roadmap | TT 70 Art. 25.4 |
| Paper made before 8 Oct 2026 | Remains valid | TT 70 Art. 25.1 |
| Receiver cannot connect online | Authenticated electronic copy accepted | TT 70 Art. 12.4, 25.3 |
| TT 89 effective | 1 Dec 2026 (portal) | https://vanban.chinhphu.vn/?docid=220070&pageid=27160 |
| TT 89 assessment file | The yearly file is "học bạ số" plus the class summary sheet; paper use and digital creation follow TT 70 | TT 89 Arts. 4, 25 |
| Paper rules in templates | Pen, red-ink, seal and hand-over rules apply only to paper "used during the transition period". **No end date given** | TT 89 Art. 22 |
| Annual creation deadline | By 30 June each year | TT 70 Art. 7.4 |
| Sync to MOET database (2025-26) | Quảng Ngãi told its Schools to sync by **20 Aug 2026**. Provincial, not a national date | QN 442/2026 |
| Pilot grades | Primary Grades 1 to 4 in 2023-24; lock dates 30 Jun and 15 Aug; provinces report by 10 Jul and 25 Aug | KH 213/2024 (mirror) |
| Schools lacking infrastructure | Quảng Ngãi told them to keep paper and plan a move for next year | QN 442/2026 |

Is a printed PDF still accepted? What the texts show:
- A printout is not the legal record. The legal record is the **signed digital record** (XML per Decision 3016, via mirror). TT 70 Art. 4.3 gives value to an electronic copy or extract made from the system and **confirmed by the School**, for the information it shows. Art. 12.5 lets a learner get a legal conversion to paper, free of charge.
- Pilot Plan 213/2024 (mirror) required that soft copies be exportable and printable in a MOET format with a lookup code.
- **No end date** for paper in TT 70 or TT 89. The only rules: already-issued paper stays valid, and paper rules apply "in the transition period" without defining it. So paper and printed copies are accepted now and until MOET sets a roadmap. "Until when" is **not answered by the sources I could read**.

## 9. Pilot 2024-25 and whether it gives vendors a spec

- Pilot documents: Plan 213/KH-BGDĐT (1 Mar 2024) and Official Letter 1396/BGDĐT-GDTH (27 Mar 2024), with follow-ups 2088 (8 May 2024) and 2781 (11 Jun 2024), then Official Letter 119/BGDĐT-GDTH (10 Jan 2025), cited by schools for three technical appendices on connection, security and integrity. I found these only as citations in search results, not the letters themselves.
- Expansion: in 2024-25 all Primary Schools were told to deploy (press: https://baoquocte.vn/ha-noi-trien-khai-hoc-ba-so-o-tat-ca-cac-truong-pho-thong-tu-nam-hoc-2024-2025-282307.html ; An Giang reports 624/624 Primary Schools, a local figure). 2025-26: Official Letter 7802/BGDĐT-GDPT (27 Nov 2025) extended to secondary and continuing education (cited by QN 442/2026).
- **Does the pilot give a vendor spec?** Not the pilot letters. They say "MOET defines the data structure and exchange method" and "solutions must meet MOET standards". The vendor-facing spec is **Decision 3016/QĐ-BGDĐT** (XML schema, signing, six API calls), updated by the CV 2239 appendix. A vendor could follow it, but I read it only through a mirror, and the mirror lists an expiry of 1 Sep 2026 I could not explain. TT 70 Art. 6.2 says MOET will set these details, so a successor or re-issue may exist.

## 10. Recommendation for the MVP

First customers are private Schools using the system from 2027. TT 70 Art. 2 covers "educational institutions delivering the general education programme", which reads as including private Schools, but the text does not say so explicitly (not verified).

**Yes. Put a scoped digital report card in the MVP.** Reasons:
- By 2027 it is the required form of the student record, not an optional extra. Schools must create it for all current and new students (TT 70 Art. 25.2). Receiving bodies may not demand extra paper once it qualifies (Art. 12.3). A school system that cannot produce it leaves the School needing a second tool.
- It sits on data the MVP already holds (profile, grades, comments, qualities, transfers). Retrofitting the data model later is expensive; adding the export later is not.
- Paper is still accepted with no end date, so a School can launch without a live link to MOET. The connection part can slip without blocking sales.

Build in the MVP:
1. Data model for the Học bạ per Level, aligned with the TT 22/27 annex templates, one record per student per school year, with a stable UUID and a lifelong-learning-record-number field (TT 70 Art. 7.1).
2. Signature **workflow state**: subject teacher, then homeroom teacher, then principal, then School signature, with locked and re-issue states and an audit trail (TT 70 Arts. 9, 10, 16).
3. XML export to MOET's schema and a printable PDF view. Needs the official XSD first.
4. Hooks for an external signing provider (remote signing and USB token) instead of building PKI.
5. Transfer: import and export of a record between Schools, with consent and a log.

Defer until the official spec and a MOET account exist:
- Live submit to the MOET database, and VNeID or Public Service Portal lookup (needs a MOET account issued via the provincial Department and the current API spec).
- Bulk digitisation of legacy paper (roadmap not published).
- Revocation API and certificate registration flow.

Get before committing (they decide effort):
1. The official text and current status of **Decision 3016/QĐ-BGDĐT** and any successor, with the XSD and API document, from MOET or a provincial Department.
2. Whether private Schools must register a certificate through the Department, and which providers they may use.
3. The archive-law retention period for học bạ and the MOET roadmap for legacy data.

## 11. Not verified

- Full text of Decision 3016/QĐ-BGDĐT, Official Letters 1396, 2088, 2781, 119, 7802 and the CV 2239 appendix. All come from mirrors, summaries or citations.
- The 1 Sep 2026 expiry of Decision 3016 (single mirror line) and what replaces it.
- The exact effective date of TT 89 (portal says 1 Dec 2026; the PDF image is handwritten and ambiguous).
- Rollout by Level and Grade: no phasing text found. The Primary pilot used Grades 1 to 4 only.
- Archive-law retention period, MOET roadmap for legacy paper, end date of paper acceptance.
- Private-School coverage and certificate provider rules; whether VNeID and Public Service Portal lookup are already live.
- TT 89 and TT 70 were read from OCR of scanned PDFs; re-check wording you hard-code.
