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
| See student profiles | ✘ | ✘ | 👁 all | 👁 all | 👁 all | 👁 all | 👁 self | 👁 linked |
| See students' sensitive details (national and Ministry IDs, Guardian contact details) | ✘ | 👁 | 👁 all | ✘ | 👁 own class | ✘ | ✘ | ✘ |
| Take attendance per period | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ own periods | ✘ | ✘ |
| See attendance | ✘ | ✘ | 👁 all | ✘ | 👁 own class | 👁 own periods | 👁 self | 👁 linked |
| Send a leave request | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ linked |
| Approve a leave request | ✘ | ✘ | ✔ | ✘ | ✔ own class | ✘ | ✘ | ✘ |
| Enter scores, submit gradebook | ✘ | ✘ | ✘ | ✘ | ✘ | ✔ own subject × class | ✘ | ✘ |
| Approve or return a gradebook | ✘ | ✘ | ✔ | ✔ own group | ✘ | ✘ | ✘ | ✘ |
| Reopen a locked gradebook (reason required, logged) | ✘ | ✘ | ✔ named by School | ✘ | ✘ | ✘ | ✘ | ✘ |
| See scores | ✘ | ✘ | 👁 all | 👁 all | 👁 all | 👁 all | 👁 self, once released | 👁 linked, once released |
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
- **Teachers read across classes**: any member with a teaching role in force (subject teacher, homeroom teacher, group leader) may see the profiles and scores of every student of the School (the matrix's "all"), read only; everything they write stays within their own scope (own class, own subject × class, own group). Sensitive details (national ID, Ministry IDs, Guardian contact details, later health data) are a separate action, visible only to the student's own homeroom teacher, the principal board and the School admin. Cross-class reads are audited from slice 7.
- **While the student is at the School** (in a class on the date, or a continuing student between two school years, until the next enrollment starts; the student and their Guardians, read only): the student's own profile, attendance, conduct and scores of **all years** (scores once released), and the class-level information of **every class the student has been in, past and current**: the class's extracurricular activities, classmates' basic profile (name, class; never contact details, date of birth, IDs or scores), the homeroom teacher and the subject teachers who taught the class, and the class's own records. A continuing student is one whose last enrollment ended with the school year (`year_end`) and who has not left.
- **After leaving the School** (transfer out, drop-out or graduation; until the end of the school year of the leaving enrollment; the student and their Guardians, read only):
  - still visible: the student's own score history and profile at this School; the class left: its extracurricular activities, classmates' basic profile, the homeroom teacher and the subject teachers who taught it;
  - no longer visible: the class's own records and everything else, including the classes of earlier years.
  After the school year ends, access to this School closes unless another link (a sibling, a new enrollment) keeps it open.
- **Class-level reads** (`class_activities.view`, `classmates.view_basic`, `class_teachers.view`, `class_records.view`) have no matrix row of their own. Staff reach them through their class scopes: the principal board in every class, a group leader in the classes where the group's subjects are taught, a homeroom teacher in the own class, a subject teacher in the classes they teach; the School admin and the operator in none. `class_records.view` is class-level content only (notices, discussions, class-level summaries); anything about one student (scores, attendance, conduct) always goes through the per-student actions (`scores.view`, `attendance.view`, `conduct.rate`) on a student, a subject × class or a class.
- **School setup is read-only for the principal board**: the board sees years, classes, subjects and role assignments (the 👁 of the first two rows) but changes none of them; only the School admin edits.
- **Named duties** (reopening gradebooks, signing for the principal) belong to principal-board rows: `can_reopen_gradebooks`, `signs_for_principal` and `title` (principal or vice principal; set once, then fixed; one principal in force at a time). They are sensitive: nobody turns one on for their own row (the School admin included), another School admin or principal-board member does; and while a self-granted principal-board row waits for its second person's confirmation, its duties cannot change.
- **Least data**: the School admin configures but sees no scores or student records unless another assignment grants it (the sensitive details of the setup's student list are the exception: the School admin enters and checks them). Operator staff see no School data; a School admin or the principal board grants support access for a fixed window, and every action in it is logged and visible to the School.
- **Digital report card** (Circular 70/2026): signatures in order (subject teachers, homeroom teacher, principal or delegate), then the School's organisational signature, applied by the principal board while the clerical role is deferred. An issued record is locked; a correction is revoke and re-issue.
- **Sign-in**: staff by email or phone number; Guardians by phone number and password, activated once with an invite code from the homeroom teacher (no SMS cost in the MVP); students by an account the School creates.
