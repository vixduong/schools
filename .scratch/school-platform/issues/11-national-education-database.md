# Must the platform sync with the national education database, and how?

Type: research
Status: resolved
Blocked by:

## Question

Vietnamese Schools report to the Ministry of Education's sector database (Cơ sở dữ liệu ngành giáo dục, csdl.moet.gov.vn) and to provincial systems. Is reporting mandatory for private Schools as well as public ones? What data, how often, and by what route: official API, file import (Excel templates), or manual entry? Do third-party school systems integrate today (for example VNEdu, SMAS, or other vendors), and is there an approval or connection procedure for vendors? Answer decides whether an export or sync belongs in the MVP and how it is built.

## Answer

Findings: branch `research/national-education-database`, file `docs/research/national-education-database.md` (not legal advice).

- Circular 42/2021/TT-BGDĐT (Art. 11.5, 17) requires preschool, general and continuing-education Schools to run school software connected to the database and to report on time. It never mentions private Schools; it regulates by Level, so they are covered by reading, not by explicit text. Confirm per province with the Sở GDĐT.
- Content and deadlines come from Circular 25/2024. Per a secondary summary: two reports a year (start of year due 30/10, end of year due 30/6), plus continuous upkeep of School, class, staff, learner and result records.
- Route: manual entry or Excel import on csdl.moet.gov.vn with a School login issued by the Sở GDĐT. Vendors connect through the Ministry's IT unit, which publishes a list of conforming software (vnEdu and MISA EMIS claim conformance). The technical spec (Decision 4998/QĐ-BGDĐT) and the onboarding steps could not be read.
- Recommendation: the MVP ships an Excel/CSV export shaped like the Ministry import templates, plus data-model fields for Ministry School/learner/teacher IDs, the national personal ID, and status history instead of deletes. API sync waits for a customer, the spec and the connection guide.
- Tension with Circular 70/2026: digital report card data must sync with the national database, so the API cannot be deferred for long; both depend on obtaining the current Ministry spec.
