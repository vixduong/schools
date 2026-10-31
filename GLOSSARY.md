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

### Assessment

**Assessment Profile**:
The rules for how students in one Level are assessed: numeric scores with weights, achievement levels with comments, or developmental observation. Attached to a Level, never to a School as a whole.
_Avoid_: Grading scheme, grading config

**Achievement Level**:
A qualitative rating used in Primary assessment (Excellent / Completed / Not completed) instead of a numeric score.
_Avoid_: Mark, rank
