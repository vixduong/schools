# Data residency and privacy for a school platform (Vietnam)

Ticket: `.scratch/school-platform/issues/02-data-residency-and-privacy.md`. Researched 2026-10-31.
**Not legal advice.** Get a Vietnamese lawyer to confirm before launch.

## Source quality caveat

thuvienphapluat.vn and luatvietnam.vn returned HTTP 403 to automated fetches, and vanban.chinhphu.vn was not reachable through search. The legal text below was read from full-text reproductions on commercial legal sites (ketoananpha.vn, hethongphapluat.com), not from the Official Gazette. Article numbers are as those pages show them. Items marked **[UNVERIFIED]** could not be confirmed. Confirm article text against the official copy before relying on it.

## Law in force by 2026

| Instrument | Status | Source |
|---|---|---|
| Personal Data Protection Law (PDPL), 91/2025/QH15, passed 26 Jun 2025 | In force 1 Jan 2026 (Art. 38) | https://ketoananpha.vn/luat-bao-ve-du-lieu-ca-nhan-nam-2025 ; metadata https://hethongphapluat.com/luat-bao-ve-du-lieu-ca-nhan-2025/khoan-1-dieu-3 |
| Decree 356/2025/NĐ-CP, dated 31 Dec 2025, implements PDPL | In force 1 Jan 2026; Decree 13/2023 repealed from that date (Art. 42) | https://ketoananpha.vn/nghi-dinh-356-2025-nd-cp |
| Data Law 60/2024/QH15 and Decree 165/2025/NĐ-CP | In force 1 Jul 2025; about "core" and "important" data, with impact reports before sending those abroad | https://digitalpolicyalert.org/event/31588-government-decree-no-1652025nd-cp-detailing-a-number-of-articles-and-measures-to-implement-the-data-law-no-602024qh15-including-data-transfer-regulation-entered-into-force (secondary) |
| Cybersecurity Law 116/2025/QH15, passed 10 Dec 2025 | In force 1 Jul 2026; replaces the 2018 Cybersecurity Law and the 2015 Law on Network Information Security | https://thuvienphapluat.vn/van-ban/cong-nghe-thong-tin/Luat-An-ninh-mang-2025-so-116-2025-QH15-666020.aspx (existence confirmed via search snippet only) |
| Decree 53/2022/NĐ-CP (guides the 2018 Cybersecurity Law) | **[UNVERIFIED]** whether it still applies after the 2025 law; a replacement decree was in draft from 13 Feb 2026 and I found no proof it was issued | https://caselaw.vn/bai-viet/toan-canh-khung-phap-ly-ve-linh-vuc-cong-nghe-thong-tin-tai-viet-nam-giai-doan-2024-2026-va-luu-y-danh-cho-doanh-nghiep-co-von-dau-tu-nuoc-ngoai-phan-1-3 |

Transition (PDPL Art. 39): consent already given under Decree 13/2023 stays valid, and impact-assessment dossiers already accepted by the authority stay valid. Source: https://ketoananpha.vn/luat-bao-ve-du-lieu-ca-nhan-nam-2025

## Findings

### 1. Is data required to be stored inside Vietnam?

- PDPL does not require in-country storage of personal data. It allows cross-border transfer subject to a filing (PDPL Art. 20; below). Source: https://ketoananpha.vn/luat-bao-ve-du-lieu-ca-nhan-nam-2025
- The data-localization duty lives in cybersecurity law. Under Decree 53/2022 Art. 26, it is triggered when the Ministry of Public Security (MPS) orders certain service providers to store user data in Vietnam. Secondary sources describe it as an on-request duty but disagree on how it applies to domestic firms: https://lsvn.vn/tu-01102022-du-lieu-nguoi-dung-internet-tai-viet-nam-se-duoc-luu-tru1661052929.html ; https://luatminhkhue.vn/thoi-gian-luu-du-lieu-cua-cong-ty-nuoc-ngoai-hoat-dong-tai-viet-nam.aspx. **[UNVERIFIED]** against the Decree text.
- An EY summary says the 2025 Cybersecurity Law keeps a duty to store user data in Vietnam for network service businesses, with no article cited: https://www.ey.com/vi_vn/technical/tax/tax-and-law-updates/luat-an-ninh-mang-2025-cua-viet-nam-cac-diem-chinh-va-yeu-cau-tuan-thu. **[UNVERIFIED]** who it covers and whether it needs an MPS order. Treat it as a possible future order, not a standing ban on Singapore.
- Data Law: "core" and "important" data may need an impact report before leaving Vietnam (Decree 165/2025). No source I found classifies school or student records as important or core data. **[UNVERIFIED]**

### 2. Cross-border transfer (applies to the Singapore VPS and R2)

- PDPL Art. 20(1) counts as a cross-border transfer: moving stored data to systems outside Vietnam, providing data to foreign parties, and using foreign platforms to process data collected in Vietnam. Decree 356 Art. 17(1)(a) says storing data on foreign servers or a foreign provider's cloud is such a transfer. So the Singapore VPS and R2 are both covered.
- Duty: prepare a cross-border transfer impact assessment (TIA) dossier and file one original with the specialized authority (MPS) within 60 days of the first transfer (PDPL Art. 20(2); Decree 356 Art. 18(4)). One assessment covers the organization's operating life and is updated on change (Art. 20(3), Art. 22).
- It is a filing, not an approval. MPS can inspect (at most once a year, or unannounced) and order a halt if the data harms national defense or security (Art. 20(4)-(5)).
- Exemptions in Art. 20(6) are state-authority transfers, employee data on cloud, and data subjects' own transfers. Decree 356 Art. 17(3) adds press, already-public data, emergencies, cross-border staff management, and contracts, logistics, payments, hotels, visas and scholarships. Cloud storage of student data is not on either list. **[UNVERIFIED]**: I could not read all of Art. 17(3) in full.
- Fines: secondary sources report up to 5% of prior-year revenue for cross-border breaches (https://www.allenandgledhill.com/vn/publication/articles/31075/upcoming-changes-to-vietnam-s-personal-data-protection-regime). **[UNVERIFIED]** against the penalty decree.
- Cloudflare R2: location hints are best effort. Only the `eu`, `fedramp` and `us` jurisdictions are guaranteed, and there is no Vietnam option: https://developers.cloudflare.com/r2/reference/data-location/. The legal point is not where the bytes sit. R2 is a foreign processor, so it is a cross-border transfer whatever its region.

### 3. Processing impact assessment (DPIA)

- Controllers must prepare an impact-assessment dossier and file it with MPS within 60 days of first processing (PDPL Art. 21). A processor (our platform, if the school is the controller) prepares and keeps its own as agreed with the controller (Art. 21(3)). Source: https://ketoananpha.vn/luat-bao-ve-du-lieu-ca-nhan-nam-2025
- Small and startup enterprises may opt out of Arts. 21, 22 and 33(2) for 5 years from 1 Jan 2026. The opt-out does not apply to firms that provide data-processing services, process sensitive data, or reach 100,000 data subjects (PDPL Art. 38; Decree 356 Art. 41). A school SaaS is a data-processing service, so assume no opt-out. Same sources.

### 4. Children and consent

- PDPL Art. 24: processing children's data follows the general rules. Legal representatives exercise the child's rights. Publicizing a child's private life or secrets needs consent from the child (age 7 or older) and the legal representative. Processing must stop if consent is withdrawn or an authority asks. Source: https://ketoananpha.vn/luat-bao-ve-du-lieu-ca-nhan-nam-2025
- I did not find in the PDPL text a general rule that all processing of minors' data needs parental consent. **[UNVERIFIED]**: needs an article-by-article check. A commentary calls this a legal gap: https://lsvn.vn/bao-ve-du-lieu-ca-nhan-cua-tre-em-theo-luat-bao-ve-du-lieu-ca-nhan-nam-2025-khoang-trong-phap-ly-va-kien-nghi-hoan-thien-a176510.html (secondary).
- Decree 356 Art. 4(1) lists sensitive data. Children and students are not named, but a catch-all covers data "required by law to be kept confidential or with strict security", plus health, biometric and behavior-tracking data. Art. 21(5) names education software "with monitoring elements" (attendance, video, behavior scoring) as a regulated service. Source: https://ketoananpha.vn/nghi-dinh-356-2025-nd-cp. Treat health, biometric and behavior data in the platform as sensitive.
- Consent must be verifiable and provable (Decree 356 Art. 6). For a school, the practical basis is the parent's consent collected at enrollment, stored as evidence, plus a processor contract between school and platform.
- Cybersecurity Law 2025: from 1 Jul 2026 a child's online account must use the parent's or guardian's details (secondary: https://hatinh.gov.vn/vi/bai-viet/luat-an-ninh-mang-co-hieu-luc-tu-172026-dat-con-nguoi-o-vi-tri-trung-tam). **[UNVERIFIED]** whether it reaches an education tool with school-created accounts.

### 5. Security duties that apply either way

Encrypt personal data at rest and in transit when using cloud, with strict access control (Decree 356 Art. 12(4)). Organizations processing sensitive data need access limits, procedures and security measures (Art. 4(2)). A data protection officer or department is addressed in Art. 13. Source: https://ketoananpha.vn/nghi-dinh-356-2025-nd-cp. **[UNVERIFIED]** whether a DPO is mandatory for us.

### 6. Public schools and education departments

- I found no Ministry of Education and Training (MOET) circular or decree that bans foreign hosting for public schools. **[UNVERIFIED]**: searches returned no MOET rule on education data hosting either way.
- State agencies are exempt from some PDPL filings (Art. 20(6), Art. 21(6)). That concerns the agency's own duties, not a vendor's.
- Government procurement of cloud for state agencies runs through separate IT and cloud rules (for example the pilot Decision 80/2014/QĐ-TTg, of uncertain current force): https://thuvienphapluat.vn/van-ban/cong-nghe-thong-tin/decision-no-80-2014-qd-ttg-the-pilot-leasing-of-information-technology-services-in-state-agencies-266582.aspx (search result only). **[UNVERIFIED]**
- Expect in practice that a provincial education department tender will require Vietnam-hosted or domestically approved cloud providers. This is my inference from how e-government projects are bought, not a cited rule.

## Recommendation

**Private Schools: Singapore + R2 is acceptable as the default, with conditions.** It is lawful in principle because PDPL permits cross-border transfer and does not require local storage. It is not free of obligations:

1. File a cross-border TIA with MPS within 60 days of first transfer, once per operating life. Use one dossier that names the VPS and R2 as destinations.
2. File the processing impact assessment (no small-business opt-out), covering the platform as processor.
3. Collect and store parent consent at enrollment, give the school a processor contract, and keep an evidence log.
4. Encrypt at rest and in transit, restrict access, and treat health, biometric and behavior-monitoring data as sensitive.
5. Use the R2 `apac` location hint. It is not a guarantee, so do not claim in-country or Singapore-only storage.
6. Keep storage portable (S3-compatible keys and a Postgres dump) so data can move to a Vietnam host if MPS issues a localization order.

Have a Vietnamese lawyer confirm points 1 to 3 and the children's-data rules before the first paying school.

**Public Schools: treat Singapore + R2 as a stopgap, not the default.** No cited rule bans it, but I could not verify the procurement rules, and education departments will probably want Vietnam-hosted or approved providers. Plan a deployment option on a Vietnamese data center or cloud provider, and ask a pilot department for its written hosting requirements before designing public-school features.

## Open questions for counsel

1. Does the 2025 Cybersecurity Law or a replacement for Decree 53/2022 impose standing localization on a school SaaS?
2. Is parental consent required for all processing of minors' data under PDPL, or only for the cases in Art. 24?
3. Do MOET or provincial departments publish hosting requirements for public-school data?
4. Is any student data "important data" under the Data Law?
