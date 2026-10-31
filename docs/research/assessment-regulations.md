# Assessment regulations per Level (as of 2026-10-31)

Resolves `.scratch/school-platform/issues/01-assessment-regulations.md`: which Ministry of Education and Training (MOET, "BGDĐT") rules govern student assessment per Level, and what an Assessment Profile must encode.

## How this was sourced

Primary sources were the signed PDFs on the Government document portal (`datafiles.chinhphu.vn`). They are scanned images with no text layer, so I OCR'd them locally (macOS Vision, Vietnamese). Digits and thresholds below were read from that OCR and cross-checked against unambiguous surrounding text. OCR can still misread a digit, so re-check any threshold you will hard-code against the PDF.

thuvienphapluat.vn and luatvietnam.vn returned HTTP 403 to automated fetches. Summaries of them by a fetch tool were wrong in places (for example the "Tốt" threshold for lower secondary), so none of their content is relied on here.

| Short name | Document | Source |
|---|---|---|
| TT 27/2020 | Circular 27/2020/TT-BGDĐT (4 Sep 2020), primary assessment regulation | Portal page: https://vanban.chinhphu.vn/default.aspx?pageid=27160&docid=201006 · PDF: https://datafiles.chinhphu.vn/cpp/files/vbpq/2020/09/27-bgddt.signed.pdf |
| TT 22/2021 | Circular 22/2021/TT-BGDĐT (20 Jul 2021), lower and upper secondary | Portal page: https://vanban.chinhphu.vn/?pageid=27160+&docid=203926 · PDF: https://datafiles.chinhphu.vn/cpp/files/vbpq/2021/08/22.signed_02.pdf |
| TT 89/2026 | Circular 89/2026/TT-BGDĐT (16 Oct 2026), amends both of the above | Portal page: https://vanban.chinhphu.vn/?docid=220070&pageid=27160 · PDF: https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/10/89-bgddt.signed.pdf |
| VBHN 01/2021 | Consolidated preschool curriculum (Circular 17/2009 as amended by 28/2016 and 51/2020) | https://caselaw.vn/van-ban-phap-luat/364454-van-ban-hop-nhat-so-01-vbhn-bgddt-ngay-13-04-2021-cua-bo-giao-duc-va-dao-tao-hop-nhat-thong-tu-ve-chuong-trinh-giao-duc-mam-non (mirror; see Preschool caveats) |

## Status summary

| Level | Governing text | In force on 2026-10-31? |
|---|---|---|
| Preschool | Preschool curriculum, section "G. Đánh giá sự phát triển của trẻ" (VBHN 01/2021). A new pilot curriculum (Decision 388/QĐ-BGDĐT, 12 Feb 2026) runs in 510 facilities from 2026-27. | Yes (consolidated text listed as in force by the mirror). The pilot's assessment rules are not verified. |
| Primary | TT 27/2020, replacing Circulars 30/2014 and 22/2016 (TT 27 Art. 3). Phased in grade by grade, grade 5 from 2024-25 (TT 27 Art. 2), so fully applied. | Yes. TT 89/2026 amends it from 1 Dec 2026 (see below). |
| Lower Secondary | TT 22/2021, replacing Circular 58/2011 and 26/2020 (TT 22 Art. 21). Phased in, grades 9 and 12 from 2024-25, so fully applied. | Yes. TT 89/2026 amends it from 1 Dec 2026. |
| Upper Secondary | Same TT 22/2021. | Same as above. |

### TT 89/2026 timing
- Signed 16 Oct 2026. The portal metadata gives effective date 01-12-2026 (portal page above). The effective-date line in the OCR'd PDF text is garbled, so I rely on the portal metadata. **As of 2026-10-31 it is not yet in force**, and a profile should be versioned with an effective date.
- Its substantive changes for the Assessment Profile are listed per Level below. Most of it concerns the digital record (Học bạ số), ownership of tests by provincial authorities, and disability handling.
- Transition clause (Art. 25): paper Học bạ continue to be usable, and digitisation follows a separate MOET roadmap on managing and using Học bạ số. That roadmap is **not** in these circulars, and I did not find it.

### Not verified
- Luật Việt Nam / the portal listing say TT 22/2021 was also amended by **Circular 10/2025/TT-BGDĐT**. I could not find its text or what it changes. The one citation of it that I saw related to commune-level People's Committee responsibilities (a likely effect of local-government reorganisation), which would not affect the profile.
- The draft amending circular was circulated in 2025 (https://moet.gov.vn/tin-tuc/du-kien-nhieu-diem-moi-trong-quy-dinh-kiem-tra-danh-gia-hoc-sinh-tieu-hoc-thcs-thpt.html). The final TT 89/2026 text is what is used here, not the draft.

---

## Primary (TT 27/2020, as amended by TT 89/2026)

**Mismatch with GLOSSARY.md.** The glossary defines Achievement Level as "Excellent / Completed / Not completed ... instead of a numeric score" for Primary. The regulation is different:
- Subject level: three levels, Hoàn thành tốt / Hoàn thành / Chưa hoàn thành (written T / H / C in the Học bạ). Source: TT 27 Art. 7.1.a and Học bạ guide.
- Whole-year level: four levels (see below), with a fourth top level.
- Numeric scores **do exist** for periodic tests (integer 1 to 10). They feed the overall rating thresholds, so Primary is not purely qualitative.
- The glossary should be reconciled with the regulation before the term is used in the design.

### What the Profile must hold

**Subjects and activities** (Học bạ template, TT 27 Phụ lục 1): Tiếng Việt, Toán, Ngoại ngữ 1, Lịch sử và Địa lí, Khoa học, Tin học và Công nghệ, Đạo đức, Tự nhiên và Xã hội, Giáo dục thể chất, Nghệ thuật (Âm nhạc), Nghệ thuật (Mĩ thuật), Hoạt động trải nghiệm, Tiếng dân tộc (optional). The grade-by-grade subject list is the curriculum, not this circular. Subjects with a scored periodic test are fixed in Art. 7.1.b (see below).

**Regular assessment (Art. 6):** comment-only, no score and no minimum count. Teachers comment orally or in writing, students self-assess, parents give feedback. Nothing to compute.

**Periodic assessment (Art. 7):**
- Four checkpoints per year: mid-term 1, end term 1, mid-term 2, end of year. At each, a subject or activity gets one of Hoàn thành tốt / Hoàn thành / Chưa hoàn thành (Art. 7.1.a).
- Written test (score 1 to 10, **integers only, no decimals**; Art. 7.1.d) at end of term 1 and end of year for: Tiếng Việt, Toán, Ngoại ngữ 1, Lịch sử và Địa lí, Khoa học, Tin học và Công nghệ (Art. 7.1.b). Grades 4 and 5 add mid-term 1 and mid-term 2 tests for Tiếng Việt and Toán only.
- Test questions are tagged with three difficulty levels (Art. 7.1.c). This affects test design, not stored results.
- A school can offer a replacement test if a result is abnormal against regular assessment (Art. 7.1.d). Học bạ stores only the last attempt (Học bạ guide).
- Qualities and competencies are rated at the same four checkpoints, as Tốt / Đạt / Cần cố gắng (Art. 7.2), for 5 qualities (yêu nước, nhân ái, chăm chỉ, trung thực, trách nhiệm), 3 general competencies (tự chủ và tự học, giao tiếp và hợp tác, giải quyết vấn đề và sáng tạo) and 7 specific competencies (ngôn ngữ, tính toán, khoa học, công nghệ, tin học, thẩm mĩ, thể chất) (Art. 5.1.b, Học bạ template).

**Annual rating (Art. 9.2.a)** (each condition is cumulative):

| Rating | Subjects and activities | Qualities and competencies | End-of-year test scores |
|---|---|---|---|
| Hoàn thành xuất sắc | all Hoàn thành tốt | all Tốt | every tested subject >= 9 |
| Hoàn thành tốt | all Hoàn thành tốt | all Tốt | every tested subject >= 7 |
| Hoàn thành | Hoàn thành tốt or Hoàn thành | Tốt or Đạt | every tested subject >= 5 |
| Chưa hoàn thành | everything else | | |

There is **no weighted average, no semester average and no rounding** at Primary. The text says "đạt 9 điểm trở lên" without saying how "every subject" is read when a subject has no test. Treat it as "every subject that has an end-of-year test".

**Completion and progression (Art. 11):**
- Hoàn thành xuất sắc / tốt / Hoàn thành means the class programme is completed. For anyone else the teacher plans supplementary assessment, and if still not met the principal tests and decides on promotion (no fixed summer re-exam format in the text).
- Grade 5: "Hoàn thành chương trình tiểu học" is recorded (Art. 11.2, reworded in TT 89/2026 Art. 5 to be confirmed in the digital Học bạ).

**Awards (Art. 13):** "Học sinh Xuất sắc" for Hoàn thành xuất sắc. "Học sinh Tiêu biểu hoàn thành tốt trong học tập và rèn luyện" for Hoàn thành tốt with an excellent subject or visible progress, recognised by the class. Ad hoc awards for special achievement.

**Học bạ content (TT 27 Phụ lục 1):** identity page, learning history by year (school, class, register number, enrolment date), height, weight, days absent with and without permission, per-subject level (T/H/C), per-subject end-of-year test score, per-subject comment, the 5 qualities and 10 competencies with level and comment, annual rating, awards, completion and promotion line, principal and homeroom teacher signatures. Class summary sheet ("Bảng tổng hợp kết quả đánh giá giáo dục của lớp", Phụ lục 2) has separate templates for mid-term, end of term 1, and end of year, for grades 1-2 and 3-5 (templates 1-9).

### Changes in TT 89/2026 relevant to Primary (from 1 Dec 2026)
- Học bạ becomes a **digital record** (Học bạ số) as part of the assessment file (Arts. 1, 3, 4). Subject teachers digitally sign their own subject results, and the homeroom teacher then digitally signs the class record (Art. 9).
- Disability assessment is rewritten (Art. 8): based on the individual education plan, a subject that the plan waives is recorded as "Miễn" (exempt), and special-skill content is recorded under "Hoạt động giáo dục kỹ năng đặc thù".
- Provincial Departments (Sở) may produce a **common end-of-term-1 and end-of-year test for grade 5** in selected scored subjects (Art. 7, new 14.1.e, and Art. 8 for schools). This is set at province level, not by the school. It does not change the rating thresholds.
- Hand-over for grade 5 (Art. 6) bars re-testing students at transfer to Lower Secondary.

### What varies by School
- Which comment wording the teacher writes, and the school's method for supplementary assessment or promotion tests (no format in the text).
- The tests in subjects the school adds beyond the six listed (the circular fixes the six but a school may also teach optional subjects such as Tiếng dân tộc).
- Provincial common tests for grade 5 (province, not school).
- Disability individual education plans are per student.
- Test content and timing are set by the school's subject groups (Art. 15.3, TT 89/2026), except where Sở supplies the grade 5 exam.

---

## Lower Secondary and Upper Secondary (TT 22/2021, as amended by TT 89/2026)

One regulation covers both. The same formulas, ratings and thresholds apply, and the Level only changes the subject list, a few THPT-only rules, and the Học bạ template.

### What the Profile must hold

**Scale and rounding (Art. 5.3.b):** 10-point scale. Other scales must convert to 10. Scores are integers or decimals "lấy đến chữ số thập phân thứ nhất sau khi làm tròn số" (one decimal place after rounding). The text does not say which rounding rule is used, so assume conventional half-up and confirm with a school's local practice.

**Subject forms (Art. 5.3):**
- Comment only (result Đạt / Chưa đạt): Giáo dục thể chất, Nghệ thuật, Âm nhạc, Mĩ thuật, Nội dung giáo dục của địa phương, Hoạt động trải nghiệm, hướng nghiệp.
- Comment plus score: every other subject in the curriculum.
- Which subject uses which form in each Grade comes from the curriculum plus this list. I did not verify the Grade-by-Grade subject list against the 2018 curriculum circular, so treat the per-Grade subject catalogue as an open input.

**Regular assessment (Art. 6):** a score taken from several assessments of the class; the teacher chooses which ones to record (Art. 6.2). Counts per semester:
- Comment-only subject: 2 assessments.
- Scored subject: depends on periods per year. The circular's text reads 35 periods per year gives 2; more than 35 up to 70 gives 3; more than 70 gives 4.
- Upper Secondary study-topic clusters ("cụm chuyên đề học tập"): the cluster counts as **one** regular score, chosen from one assessment per topic (Art. 6.3). No periodic test applies to it (Art. 7.1).

**Periodic assessment (Art. 7):**
- Per semester: 1 mid-term and 1 end-of-term (score or comment). Written test length: 45 minutes for subjects up to 70 periods per year, 60 to 90 minutes above 70, up to 120 minutes for specialised subjects of selective schools (Art. 7.1).
- Make-up is allowed for force majeure. Otherwise the missing item counts as Chưa đạt or **0 points** (Art. 7.4, 7.5).
- TT 89/2026 Art. 15 adds computer-based periodic tests, allowed only when the school meets MOET's facility, IT and software conditions. Results are legally equal to paper, and a technical failure triggers a re-test or paper test within 7 working days. TT 89/2026 Art. 14 adds that specialised classes in selective upper-secondary schools follow their school and subject-group plan without increasing the number of periodic tests.

**Subject averages (Art. 9.1):**
- Semester average: `ĐTBmhk = (TĐĐGx + 2 x ĐĐGgk + 3 x ĐĐGck) / (Số ĐĐGx + 5)`. Weights: regular score 1, mid-term 2, end-of-term 3.
- Full-year average: `ĐTBmcn = (ĐTBmhk I + 2 x ĐTBmhk II) / 3`.
- Comment-only subject, semester: Đạt only if the required number of assessments were taken and **all** are Đạt, otherwise Chưa đạt. Full year equals the semester 2 result (Art. 9.1.a).

**Overall learning rating, per semester and full year (Art. 9.2).** Four levels, cumulative conditions:

| Level | Comment-only subjects | Scored subjects |
|---|---|---|
| Tốt | all Đạt | every ĐTB >= 6.5, and at least 6 subjects >= 8.0 |
| Khá | all Đạt | every ĐTB >= 5.0, and at least 6 subjects >= 6.5 |
| Đạt | at most 1 Chưa đạt | at least 6 subjects >= 5.0, and none < 3.5 |
| Chưa đạt | everything else | |

Adjustment (Art. 9.3): if the level fell two or more steps **only** because of one subject, raise it one step.

There is no overall average across all subjects. A rating comes from per-subject averages only.

**Conduct, called "kết quả rèn luyện" (Art. 8).** Four levels, Tốt / Khá / Đạt / Chưa đạt, set by the homeroom teacher against the qualities in the curriculum (subject teachers give input). It is **not a score**. The full-year level is derived from the two semesters:

| Full year | Semester 2 | Semester 1 |
|---|---|---|
| Tốt | Tốt | Khá or better |
| Khá | Khá | Đạt or better |
| Khá | Đạt | Tốt |
| Khá | Tốt | Đạt or Chưa đạt |
| Đạt | Đạt | Khá, Đạt or Chưa đạt |
| Đạt | Khá | Chưa đạt |
| Chưa đạt | all other combinations | |

TT 89/2026 Art. 16 adds: for a student serving a disciplinary measure, the homeroom teacher re-rates conduct after the measure is completed and recognised by the school.

**Promotion or graduation (Art. 12)**, all of:
1. Full-year conduct Đạt or better (including re-rating after summer training).
2. Full-year learning Đạt or better (including re-assessment, below).
3. No more than **45 absence sessions** per year, counted at 1 session per day, with or without permission, continuous or not.
Otherwise the student is held back, or does not complete the Lower or Upper Secondary programme. For students with disabilities the principal decides using Art. 11 (individual education plan).

**Summer conduct training (Art. 13):** a student with full-year conduct Chưa đạt does summer training. The principal defines the format. The homeroom teacher assigns the tasks, parents sign a report, and the teacher asks the principal to re-rate the full-year conduct. The re-rated result replaces the full-year result for promotion.

**Re-assessment of subjects in summer (Art. 14, replaced by TT 89/2026 Art. 19):**
- Current text (until 1 Dec 2026): a student who fails promotion but has full-year conduct Đạt or better and full-year learning Chưa đạt is re-assessed in each comment-only subject rated Chưa đạt and each scored subject with ĐTBmcn < 5.0. The re-assessment result **replaces** that subject's full-year result when re-checking promotion.
- New text (from 1 Dec 2026): the same, but conduct is the full-year conduct **including summer training**. A student whose conduct was Chưa đạt becomes eligible for re-assessment only if summer training lifts conduct to Đạt or better. A student with both full-year learning and conduct Chưa đạt, without summer training completed, is **not** eligible. New Art. 13.4: for grades 9 and 12, re-assessment dates are flexible and the Sở sets completion dates ahead of admission and graduation recognition.
- Practical effect on the model: the profile needs a re-assessment record per subject, the original full-year result kept alongside the replacement, and an eligibility check that depends on conduct.

**Exemptions (Art. 10):** students with chronic illness, disability, accident, or illness treated are exempted from the **practical part** of Giáo dục thể chất and Giáo dục quốc phòng và an ninh (the latter in Upper Secondary). The principal approves per semester or year, on an application plus a hospital certificate from district level or above. They are assessed on theory instead, so the number of assessments stays the same.

**Disability (Art. 11, replaced by TT 89/2026 Art. 17):** assessed on progress against the student's individual education plan, with waived subjects recorded as exempt. TT 89/2026 points to TT 27 Art. 8 (as rewritten) for the principles.

**Awards (Art. 15):**
- "Học sinh Xuất sắc": full-year conduct Tốt, full-year learning Tốt, and at least 6 scored subjects with ĐTBmcn >= 9.0.
- "Học sinh Giỏi": full-year conduct Tốt and learning Tốt.
- Ad hoc awards, and recommendation for higher-level awards.

**Học bạ content (TT 22 Phụ lục):**
- Page 1: identity, parents or guardian, learning history per year, principal signature and seal.
- Per class-year page: for each subject, the average or level for semester 1, semester 2 and full year; the average or level after re-assessment or summer training; the subject teacher's comment and signature.
- Per-year summary: conduct and learning level for semester 1, semester 2 and full year; total absence sessions; levels after summer re-assessment; promoted or not; at final grade of the Level, whether the programme was completed; certificates; competition results; awards; summer conduct result; homeroom teacher's comment.
- Lower Secondary subjects on the template: Ngữ văn, Toán, Ngoại ngữ 1, Giáo dục công dân, Lịch sử và Địa lí, Khoa học tự nhiên, Công nghệ, Tin học, Giáo dục thể chất, Nghệ thuật, Hoạt động trải nghiệm hướng nghiệp, Nội dung giáo dục của địa phương, Tiếng dân tộc thiểu số, Ngoại ngữ 2.
- Upper Secondary subjects on the template: Ngữ văn, Toán, Ngoại ngữ 1, Giáo dục thể chất, Giáo dục quốc phòng và an ninh, Hoạt động trải nghiệm hướng nghiệp, Nội dung giáo dục của địa phương, Vật lí, Hóa học, Sinh học, Lịch sử, Địa lí, Giáo dục kinh tế và pháp luật, Công nghệ, Tin học, Âm nhạc, Mĩ thuật, Tiếng dân tộc thiểu số, Ngoại ngữ 2.
- TT 89/2026 Art. 22: for the digital Học bạ the fields and assessment content on the template define the professional content. The paper-specific rules (pen colour, red-ink corrections, seals, handover) apply only to paper Học bạ still in use during transition. Digital rules (signing, issue, correction, storage) follow MOET's Học bạ số regulation (not found).

**Other changes in TT 89/2026 for secondary:**
- Sở sets a common end-of-term-1 and end-of-term-2 test for **grades 9 and 12** in selected scored subjects (Art. 20.2 new Art. 16.5, Art. 21 new Art. 18.7). Schools run it and mark it. This is decided by the province, not the school.
- Scope now explicitly covers multi-level schools, specialised schools, and selective-programme (chuyên) classes (Art. 12).

### Differences between Lower and Upper Secondary
- Subject catalogue and Học bạ template (above).
- "Cụm chuyên đề học tập" (study-topic clusters) exist only in Upper Secondary.
- Giáo dục quốc phòng và an ninh and its practical exemption exist only in Upper Secondary.
- Upper Secondary has elective subjects per student, so the scored-subject list is per student, not per Grade. The regulation does not cap how many electives count toward "at least 6 scored subjects"; the six-subject rule applies to whatever scored subjects the student takes.
- Grade 9 completes Lower Secondary. Grade 12 completes Upper Secondary. Both get the common provincial test under TT 89/2026.

### What varies by School
- **Set by the principal or school:** summer training format (Art. 13.2); which regular assessments to record and when, via the subject group's plan (Art. 6.2); test dates within the semester; whether to run computer-based tests (only when MOET conditions are met); whether to add subjects from the local content, ethnic-minority language, second foreign language lists; which student gets a practical exemption (principal approval); promotion decisions for students with disabilities.
- **Set by the province (Sở) and not the school:** the common grade 9 and 12 tests, and the timing of grade 9 and 12 re-assessment.
- **Not variable by school (fixed by the circular):** the formulas, weights, thresholds, level names, 45-session absence limit, comment-only subject list, number of regular assessments per period band, and award criteria.

---

## Preschool

Preschool has no scoring, no ratings and no promotion decision in the sources I could verify.

**Governing text.** The preschool curriculum (Circular 17/2009/TT-BGDĐT as amended by 28/2016 and 51/2020, consolidated in 01/VBHN-BGDĐT, 13 Apr 2021), Part 4 section "G. Đánh giá sự phát triển của trẻ". The caselaw.vn mirror lists it as in force. I could not open the official copy on `vanban.chinhphu.vn`, so this is a mirror, not a primary source. It is quoted as follows.

**What an Assessment Profile for Preschool holds** (VBHN 01/2021, section G, kindergarten version):
- Two assessment kinds:
  1. **Daily assessment**: health status; emotional state, attitude and behaviour; knowledge and skills. Methods: observation, conversation, analysing the child's work, talking to parents or carers. The teacher notes marked changes daily and adjusts the plan.
  2. **Stage assessment**: development in 5 domains (physical, cognition, language, emotion and social skills, aesthetics; the text lists them as "thể chất, nhận thức, ngôn ngữ, tình cảm và kỹ năng xã hội, thẩm mĩ"). At the end of each theme or month, and at the end of each age band. Methods add situational tasks or exercises. Results are kept in the child's personal file. Physical development additionally uses weight and height at the end of the age band.
- Reference: the curriculum's goals and "expected outcomes" per age band. The nursery text lists age points of 6, 12, 18, 24 and 36 months in the earlier consolidated wording.
- No levels, thresholds or averages are defined. The profile is a set of **domains, observation frequency, methods, and the stored result type**, which the regulation leaves unspecified (free text or checklist in the child's file).

**Other things that stop this being a clean profile:**
- The separate "Bộ chuẩn phát triển trẻ em năm tuổi" (Circular 23/2010) was **repealed by Circular 21/2024/TT-BGDĐT from 14 Jan 2025**, because its content was said to be integrated into the preschool curriculum (listing of 23/2010 as item 7: https://caselaw.vn/van-ban-phap-luat/412026-thong-tu-so-21-2024-tt-bgddt-ngay-28-11-2024-cua-bo-truong-bo-giao-duc-va-dao-tao-bai-bo-van-ban-quy-pham-phap-luat-do-bo-truong-bo-giao-duc-va-dao-tao-ban-hanh-va-lien-tich-ban-hanh-trong-linh-vuc-giao-duc; reason given by a news report, not the circular: https://voh.com.vn/giao-duc/bo-gd-dt-bai-bo-11-thong-tu-quyet-dinh-cu-chuyen-doi-mo-hinh-quan-ly-giao-duc-570089.html). Schools and provinces may still use tools built on it.
- **New pilot curriculum.** Decision 388/QĐ-BGDĐT (12 Feb 2026) approves a pilot preschool curriculum for 2026-27, with Dispatch 2595/BGDĐT-GDMN (14 May 2026) listing 510 participating facilities (https://luatvietnam.vn/tin-van-ban-moi/chinh-thuc-thi-diem-chuong-trinh-giao-duc-moi-tai-truong-mam-non-186-108975-article.html). I could not read the decision or the dispatch, so I do not know whether its assessment method differs. Plan for a per-school (pilot or not) switch.
- School records for care, nutrition and education (Circular 52/2020 school charter, Art. 21 as cited by a local decision) were not read. Whether those fields belong in the Assessment Profile is open.
- The 2026 consolidated text 08/VBHN-BGDĐT I opened (https://datafiles.chinhphu.vn/cpp/files/vbpq/2026/7/08-vbhn-bgddt.signed.pdf) is about the standards for **drafting** the curriculum (Circular 49/2020 as amended by 51/2026) and is not about child assessment.

### What varies by School (Preschool)
Almost everything. The regulation gives principles and the teacher's methods, not results. The school (and province) chooses the plan, observation tools, themes and months for stage assessment, and the form of the personal file. Optional content a school adds (foreign language, digital skills; VBHN 01/2021 Part 4, point 1) is assessed by the school's own plan.

---

## Implications for the Assessment Profile model

1. A profile needs a **type** with different shapes, not one config schema:
   - `numeric-weighted` (Lower and Upper Secondary): subjects with form (score or comment), regular-score count by period band, weights 1/2/3, year weights 1/2, rounding to 1 decimal, thresholds table, adjustment rule, promotion rules, re-assessment, summer conduct.
   - `level-with-test-scores` (Primary): 3-level subject ratings at four checkpoints, 3-level quality ratings, integer test scores for named subjects, the 4-level annual rating with test-score floors.
   - `developmental-observation` (Preschool): domains, frequency, methods, stored result.
2. Promotion, awards and conduct rules are tied to the profile but computed from the Level's data.
3. **Versioning with an effective date is required.** TT 89/2026 changes re-assessment eligibility, adds digital record, province-set common tests, and disability handling on 1 Dec 2026, mid-school-year.
4. Provincial authority (Sở) is an actor that sets some assessments. The current profile-to-School relationship does not capture "set by province".
5. Digital record (Học bạ số) management rules are in a MOET regulation I did not find. Do not model Học bạ signing flow until it is read.
6. Items I could not resolve: Circular 10/2025's effect, the pilot preschool curriculum's assessment method, the Học bạ số regulation, per-Grade subject lists under the 2018 curriculum, and the rounding rule.
