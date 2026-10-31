# Who are the users, and what may each role see and change?

Type: grilling
Status: resolved
Blocked by:

## Question

Settle the role model: School admin, principal board, homeroom teacher, subject teacher, student, parent, and the platform operator. Key edge cases: a teacher who is homeroom in one class and subject teacher in others; a parent with children in two different Schools (one login or two?); a student who transfers between Schools mid-year (does their history follow them?); who may edit a score after the gradebook is locked. Output: role list, permission matrix, glossary terms.

## Comments

- Round 1 (owner): Q1 accepted; **deferred roles recorded**: clerical staff (văn thư), accountant (kế toán), school nurse (y tế) come after the MVP. Q2 to Q5, Q7, Q8 accepted as recommended. Q6 changed: Lower and Upper Secondary students get accounts to view grades, timetable and notices **and to take tests that teachers author and publish online**; Primary and Preschool students have no account.
- Round 2 (owner): Q9 extended: regular tests include short 15 and 30-minute quizzes, published by the subject teacher alone; periodic tests need the group leader's approval. Q10 to Q15 accepted as recommended. Draft matrix: `docs/roles.md`.
- Round 3 (owner): Q16 to Q19 accepted as recommended (lesson visibility, who notifies whom, who issues Guardian invite codes, who reads the audit log).

## Answer

Recorded in `docs/roles.md` (model, roles, permission matrix, rules) and ADR 0002; terms in `GLOSSARY.md` (Account, Membership, Role Assignment, Guardian, Enrollment).

- One Account per person across the platform, one Membership per School, one session per School subdomain. Permissions come from Role Assignments in force: role × scope × school year.
- Eight MVP roles: platform operator, School admin, principal board, subject group leader, homeroom teacher, subject teacher, student (Lower/Upper Secondary only), Guardian. Clerical staff, accountant and nurse come after the MVP.
- Gradebook: teacher submits, group leader or principal board approves or returns, approval locks, only the named principal board member reopens with a reason. The homeroom teacher reads all subjects of the class.
- Online tests: students take tests teachers publish. Regular tests, including 15 and 30-minute quizzes, need no approval; periodic tests need the group leader's. Time window, duration, attempt limit, shuffling; results only when released; into the gradebook only when the teacher pushes them.
- Least data: the School admin configures but sees no scores; operator access only through time-limited grants logged for the School.
- Transfers: records stay with the School; the report card moves by the official route.
