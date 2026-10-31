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

**Guardian**:
An adult who answers for a student to the School: a parent, grandparent or other carer, linked to one or more students.
_Avoid_: Parent (in English text, as a type), phụ huynh (in English text)

**Enrollment**:
A student's place in one School for one school year, in one class. A transfer ends one Enrollment and starts another in the new School; records stay with the School that made them.
_Avoid_: Registration, admission

### Assessment

**Assessment Profile**:
The rules for how students in one Level are assessed: numeric scores with weights, achievement levels with comments, or developmental observation. Attached to a Level, never to a School as a whole.
_Avoid_: Grading scheme, grading config

**Achievement Level**:
The rating a Primary subject receives at each checkpoint: Hoàn thành tốt, Hoàn thành or Chưa hoàn thành. Primary also records integer test scores; the two sit side by side and are never averaged.
_Avoid_: Mark, rank, grade

**Assessment Profile Version**:
One dated edition of an Assessment Profile, tied to the regulation in force from its effective date; a school year is assessed under the version in force for it.
_Avoid_: Ruleset, config version
