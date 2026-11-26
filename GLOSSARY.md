# School Platform

A multi-tenant school management product for Vietnamese schools, from preschool to upper secondary, served from one codebase.

## Language

### Organization

**School**:
One school organization that subscribes to the platform; the unit of tenancy and data isolation.
_Avoid_: Tenant (in user-facing or domain text), customer, campus

**School Chain**:
A group that owns several Schools. Each member is a separate School; the chain itself is not modeled.
_Avoid_: Organization, system

**Level**:
One stage of schooling a School teaches: Preschool, Primary, Lower Secondary, or Upper Secondary. A multi-level School teaches several.
_Avoid_: Grade (that is a year within a Level), cấp (in English text)

**Grade**:
A year of study within a Level, e.g. Grade 7.
_Avoid_: Khối (in English text), year

### People

**Account**:
One person's login on the platform, shared across every School they belong to.
_Avoid_: User (when the School-specific membership is meant), profile

**Membership**:
An Account's presence in one School; everything a person can do in a School hangs off their Membership there.
_Avoid_: Tenant user, school account

**Role Assignment**:
A Membership's duty in one scope for one school year, such as homeroom teacher of 7A or subject teacher of Maths in 7A and 7B. Permissions come from the assignments in force, never from an account type.
_Avoid_: Account type, user type, role (alone, when the scoped assignment is meant)

**Invitation**:
A School's statement that a person is expected, and as what (staff with their Role Assignments, Guardian of a student, or the student themself), carried by a one-time code. The person activates it on the School's host, creating their Account or proving they own one; a School never creates an Account itself.
_Avoid_: Invite code (for the whole record; the code is one part of it), account creation

**Audit log**:
The School's append-only record of who changed or saw what: role, membership, invitation, student, enrollment and Guardian-link changes, full views of sensitive details, and every support grant and operator command. Read by the School admin and the principal board; no one edits or deletes an entry.
_Avoid_: History (for the log; a row's own history is its periods and events), activity feed

**Support grant**:
A School's time-limited permission (1 to 72 hours) for the platform operator to read its data, for a stated reason. The operator uses it only through a logged, read-only server command.
_Avoid_: Impersonation, admin access

**Import batch**:
One uploaded Excel file of staff, students or Guardians: its rows as checked at the preview, applied all together or not at all at the commit. Imports create students, Enrollments and Invitations, never Accounts.
_Avoid_: Upload (for the record), sync

**Guardian**:
An adult who answers for a student to the School: a parent, grandparent or other carer, linked to one or more students.
_Avoid_: Parent (in English text, as a type), phụ huynh (in English text)

**Enrollment**:
A student's place in one School for one school year, in one class. A transfer ends one Enrollment and starts another in the new School; records stay with the School that made them.
_Avoid_: Registration, admission

### Assessment

**Carried results**:
The scores a student who arrives during a term brings from the previous School, entered by the homeroom teacher with the source School and the transfer document. They sit beside this School's own scores in the gradebook and never replace one; they are never read from another School's data.
_Avoid_: Imported scores, transferred grades

**Semester average**:
A student's average in one scored subject for one term (ĐTBmhk), from the regular, mid-term and end-term scores with the weights of the Assessment Profile Version, one decimal. Calculated on read, never stored; final once the gradebook is approved, provisional before. A comment-only subject has a result (Đạt / Chưa đạt) instead.
_Avoid_: GPA, mean, term grade

**Year average**:
A student's average in one scored subject for the school year (ĐTBmcn), from the two semester averages (semester 2 weighted double), shown only in the second semester's gradebook of a two-term year.
_Avoid_: Final grade, annual score

**Previous semester average**:
The first-semester average of a student who arrived in semester 2, brought from the previous School as one Carried result per scored subject; the year average uses it when the student has no semester 1 gradebook here.
_Avoid_: Imported average, transferred average

**Assessment Profile**:
The rules for how students in one Level are assessed: numeric scores with weights, achievement levels with comments, or developmental observation. Attached to a Level, never to a School as a whole.
_Avoid_: Grading scheme, grading config

**Achievement Level**:
The rating a Primary subject receives at each checkpoint: Hoàn thành tốt, Hoàn thành or Chưa hoàn thành. Primary also records integer test scores; the two sit side by side and are never averaged.
_Avoid_: Mark, rank, grade

**Assessment Profile Version**:
One dated edition of an Assessment Profile, tied to the regulation in force from its effective date; a school year is assessed under the version in force for it.
_Avoid_: Ruleset, config version

### Communication

**Notice**:
A title and a plain-text body from one sender to an audience; its recipients are fixed at sending, and a sent Notice is never edited or deleted. Each recipient reads it in the app, and is emailed when their Account has an email.
_Avoid_: Announcement, message, thông báo (in English text)

**Audience**:
Who a Notice reaches, one of four, each tied to one scope of the "Send notices" row: the whole School (Guardians and students), a group's subject teachers, a class's Guardians, or a class's Guardians and students. The sender is never a recipient.
_Avoid_: Recipient list, distribution list, target

**Read mark**:
The first time a recipient opens a Notice; set once, and the sender sees only the count of them, never who read.
_Avoid_: Seen, read receipt
