# What do Vietnamese law and public-school buyers require of where student data is stored?

Type: research
Status: resolved
Blocked by:

## Question

Under Decree 13/2023/ND-CP and any later personal-data law or decrees in force in 2026 (and cybersecurity/data-localization rules), what does storing student and parent data — much of it about children — require: consent from parents, data stored inside Vietnam, impact assessments, cross-border transfer filings? Does hosting in Singapore with files on Cloudflare R2 comply for private Schools? Do public Schools or education departments require in-country hosting or approved providers? Answer decides whether R2/Singapore is the default or only a stopgap.

## Answer

Findings: branch `research/data-residency-and-privacy`, file `docs/research/data-residency-and-privacy.md` (not legal advice).

- The Personal Data Protection Law 91/2025/QH15 and Decree 356/2025/ND-CP took effect on 1 Jan 2026 and replace Decree 13/2023. Effective dates and numbers spot-checked against PwC Vietnam and EY Vietnam alerts.
- Neither law requires storing data in Vietnam. Hosting on a Singapore VPS and on R2 counts as a cross-border transfer: file a transfer impact assessment with the Ministry of Public Security within 60 days of the first transfer, plus a processing impact assessment. A school SaaS cannot use the small-business exemption.
- Children: the only child-specific consent rule found covers publicizing a child's private life. Collect parent consent at enrollment anyway, and sign a processor contract with each School.
- Recommendation: Singapore + R2 (with the `apac` hint) is acceptable for private Schools, provided the filings and consent are in place and storage stays portable. For public Schools it is a stopgap; plan a Vietnam-hosted option for tenders.
- Unverified: whether the 2025 Cybersecurity Law (in force 1 Jul 2026) imposes standing localization; the status of Decree 53/2022; public-school procurement rules.
