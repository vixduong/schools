# Roles and permissions

Decided in the ticket *Who are the users, and what may each role see and change?* (`.scratch/school-platform/issues/04-roles-and-permissions.md`). Terms follow `GLOSSARY.md`.

## Model

- One **Account** per person across the platform; one **Membership** per School it belongs to; signed in per School subdomain, one session per School.
- Permissions come from **Role Assignments** in force: role × scope (School, Grade, class, subject, subject group) × school year. A person may hold several at once (homeroom teacher of 7A, Maths teacher of 7A and 7B, Maths group leader, Guardian of a Grade 3 student). Last year's assignments expire; their history stays.
- A student and a Guardian get no Role Assignment rows: a student's rights come from `Student.membership` + Enrollment, a Guardian's from a `GuardianLink`, so each link has one source of truth (the Role Assignment roles are the staff roles only).
- Records belong to the School that made them. A transfer ends one **Enrollment** and starts another; the report card moves by the official route, never by sharing data between Schools.

## Roles (MVP)

| Role | Scope | In one line |
|---|---|---|
| Platform operator | the platform | runs the service; no access to School data unless granted |
| School admin | School | configures the School: years, classes, subjects, accounts, assignments |
| Principal board (hiệu trưởng, phó hiệu trưởng) | School | sees everything academic, approves, reopens locked records |
| Subject group leader (tổ trưởng chuyên môn) | subject group | approves gradebooks and periodic tests of the group |
| Homeroom teacher (giáo viên chủ nhiệm) | class | owns the class: leave requests, attendance overview, conduct rating |
| Subject teacher (giáo viên bộ môn) | subject × classes | teaches: attendance per period, scores, lessons, tests |
| Student | own record | Lower and Upper Secondary only: views own data, takes published tests |
| Guardian | linked students | views the linked students' data, sends leave requests |

Deferred past the MVP: clerical staff (văn thư), accountant (kế toán), school nurse (y tế).

## Permission matrix

✔ = may · 👁 = read only · ✘ = no. "Own" means within the assignment's scope.

| Action | Operator | School admin | Principal board | Group leader | Homeroom | Subject teacher | Student | Guardian |
|---|---|---|---|---|---|---|---|---|
| Configure School, years, classes, subjects | ✘ | ✔ | 👁 | ✘ | ✘ | ✘ | ✘ | ✘ |
| Create accounts, import from Excel, assign roles | ✘ | ✔ | 👁 | ✘ | ✘ | ✘ | ✘ | ✘ |
| Issue Guardian invite codes | ✘ | ✔ | ✘ | ✘ | ✔ own class | ✘ | ✘ | ✘ |
| See student profiles | ✘ | ✘ | 👁 all | 👁 group's classes | 👁 own class | 👁 own classes | 👁 self | 👁 linked |
| Take attendance per period | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ own periods | ✘ | ✘ |
| See attendance | ✘ | ✘ | 👁 all | ✘ | 👁 own class | 👁 own periods | 👁 self | 👁 linked |
| Send a leave request | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ linked |
| Approve a leave request | ✘ | ✘ | ✔ | ✘ | ✔ own class | ✘ | ✘ | ✘ |
| Enter scores, submit gradebook | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ own subject × class | ✘ | ✘ |
| Approve or return a gradebook | ✘ | ✘ | ✔ | ✔ own group | ✘ | ✘ | ✘ | ✘ |
| Reopen a locked gradebook (reason required, logged) | ✘ | ✘ | ✔ named by School | ✘ | ✘ | ✘ | ✘ | ✘ |
| See scores | ✘ | ✘ | 👁 all | 👁 own group | 👁 own class, all subjects | 👁 own subject × class | 👁 self, once released | 👁 linked, once released |
| Rate conduct (end of term) | ✘ | ✘ | 👁 | ✘ | ✔ own class | ✘ | 👁 self | 👁 linked |
| Author and publish lessons | ✘ | ✘ | 👁 | 👁 group's | ✘ | ✔ own subject | 👁 published to own class | ✘ |
| Author a test; publish a regular test (incl. 15 and 30-minute quizzes) | ✘ | ✘ | 👁 | 👁 | ✘ | ✔ own subject × class | ✘ | ✘ |
| Approve a periodic test (mid-term, end of term) before publishing | ✘ | ✘ | ✔ | ✔ own group | ✘ | ✘ | ✘ | ✘ |
| Take a published test | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ own class, in its window | ✘ |
| Grade, release results, push to a gradebook column | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ own tests | ✘ | ✘ |
| Send notices | ✘ | ✔ whole School | ✔ whole School | ✔ own group | ✔ own class's Guardians | ✔ own classes | ✘ | ✘ |
| Sign the digital report card: own subject's results | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ own subject × class | ✘ | ✘ |
| Sign the digital report card: the class | ✘ | ✘ | ✘ | ✘ | ✔ own class | ✘ | ✘ | ✘ |
| Sign as principal and apply the School's organisational signature | ✘ | ✘ | ✔ principal or delegate | ✘ | ✘ | ✘ | ✘ | ✘ |
| Export Ministry reports (Excel) | ✘ | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Grant time-limited support access to the operator | ✘ | ✔ | ✔ | ✘ | ✘ | ✘ | ✘ | ✘ |
| Read the audit log | ✘ | 👁 | 👁 | ✘ | ✘ | ✘ | ✘ | ✘ |

## Rules behind the matrix

- **Gradebook**: subject teacher enters and submits; the group leader (or the principal board) approves or returns with a comment; approval locks it; only the principal board member the School names may reopen, with a reason; every edit after a reopen is logged. The homeroom teacher sees all subjects of the class but edits none.
- **Online tests**: regular tests, including 15 and 30-minute quizzes, are published by the subject teacher alone; periodic tests need the group leader's approval first. Every test has a time window and a duration, a limit on attempts, and shuffled questions and answers; no proctoring or browser lock in the MVP. Results reach students and Guardians only when the teacher releases them; answers and worked solutions only if the teacher chooses. A result enters the gradebook only when the teacher pushes it into a chosen column; from there the gradebook workflow applies.
- **Leave request**: a Guardian sends it; the homeroom teacher approves or declines; it is a ticket with a lifecycle (waiting, approved, declined).
- **After a transfer out** (until the end of that school year; the student and their Guardians, read only):
  - still visible: the student's own score history and records at this School; the class's extracurricular activities; classmates' basic profile (name, class; never contact details, date of birth, IDs or scores); the homeroom teacher and the subject teachers who taught the class;
  - no longer visible: the class's own records (class gradebooks, class attendance and conduct logs, class notices and discussions).
  After the school year ends, access to this School closes unless another link (a sibling, a new enrollment) keeps it open.
- **Least data**: the School admin configures but sees no scores or student records unless another assignment grants it. Operator staff see no School data; a School admin or the principal board grants support access for a fixed window, and every action in it is logged and visible to the School.
- **Digital report card** (Circular 70/2026): signatures in order (subject teachers, homeroom teacher, principal or delegate), then the School's organisational signature, applied by the principal board while the clerical role is deferred. An issued record is locked; a correction is revoke and re-issue.
- **Sign-in**: staff by email or phone number; Guardians by phone number and password, activated once with an invite code from the homeroom teacher (no SMS cost in the MVP); students by an account the School creates.
