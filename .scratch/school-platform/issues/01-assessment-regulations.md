# Which Vietnamese assessment regulations must each Assessment Profile encode?

Type: research
Status: resolved
Blocked by:

## Question

For each Level (Preschool, Primary, Lower Secondary, Upper Secondary), which Ministry of Education circulars currently govern student assessment (expected: Circular 22/2021 for secondary, Circular 27/2020 for primary, the current preschool programme rules), including any amendments in force as of 2026? Extract what an Assessment Profile must encode: score columns and their counts per subject, weights, rounding, term/year averages, achievement and conduct ratings and their thresholds, comment-only subjects, re-examination rules, and what goes on the official report card (học bạ). Flag anything that varies by School.

## Answer

Findings: branch `research/assessment-regulations`, file `docs/research/assessment-regulations.md` (official PDFs were OCR'd; re-check any threshold against the PDF before hard-coding it).

- Lower + Upper Secondary: Circular 22/2021. Subjects are either scored (10-point, 1 decimal) or comment-only (Đạt/Chưa đạt). Each semester has 2/3/4 regular scores by periods per year, plus one mid-term and one end-of-term. Semester average = (Σ regular + 2×mid + 3×end) / (n + 5). Year average = (S1 + 2×S2) / 3. Learning is rated Tốt/Khá/Đạt/Chưa đạt; conduct is a 4-level rating; promotion also caps absences at 45 sessions. Rounding rule is not stated (assume half-up).
- Primary: Circular 27/2020. Subjects are rated Hoàn thành tốt/Hoàn thành/Chưa hoàn thành at four checkpoints; qualities and competencies are Tốt/Đạt/Cần cố gắng; integer 1–10 test scores in 6 subjects at the end of term 1 and the end of the year. No averages.
- Preschool: development across 5 domains, daily and per stage, with no scores or levels. Almost everything is defined by the School.
- Amendment: Circular 89/2026 (effective 1 Dec 2026, not yet in force) amends both circulars: a digital report card (học bạ số), summer re-training for conduct, and province-set common tests. **Version every Assessment Profile by effective date.**
- Varies by School: re-training format, which regular assessments are recorded, test dates, optional subjects, and nearly all of Preschool. Formulas, thresholds and level names are fixed by the circulars.
