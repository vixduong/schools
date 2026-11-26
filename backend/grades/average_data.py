"""The inputs of `averages.py` for a gradebook's roster, read in a fixed number of queries
whatever the roster's size: the book's columns and current cells, the students' carried results,
the term's place in its school year, the gradebooks that split a student, and, in a semester 2
book of a scored subject, each student's semester 1 gradebook with its cells."""

from dataclasses import asdict

from django.db import models

from schools.models import Enrollment, Subject, Term

from . import averages
from .models import CarriedResult, Gradebook, GradebookColumn, ScoreEntry

PREVIOUS = CarriedResult.Kind.PREVIOUS_SEMESTER_AVERAGE


def term_position(term):
    """(terms in the term's school year, terms of it ending before this one starts)."""
    others = list(Term.objects.filter(school_year_id=term.school_year_id).values_list("ends_on"))
    return len(others), sum(ends_on < term.starts_on for (ends_on,) in others)


def during(term):
    """Enrollments in force at any time during `term`."""
    return Enrollment.objects.filter(
        models.Q(valid_to__isnull=True) | models.Q(valid_to__gte=term.starts_on),
        valid_from__lte=term.ends_on,
    )


def required(columns, assessment):
    """The (kind, index) cells an average needs: every column of a scored subject; the regular
    comments of a comment-only one (docs/slices/1b-slice-1.md, Terms)."""
    return [
        (c.kind, c.index)
        for c in columns
        if assessment == Subject.Assessment.SCORED or c.kind == GradebookColumn.Kind.REGULAR
    ]


def current_cells(books, student_ids):
    """{(gradebook id, student id): {(kind, index): value or result}}: the current entries that
    are not cleared (filtered after DISTINCT ON, which runs after a WHERE)."""
    entries = (
        ScoreEntry.objects.filter(column__gradebook__in=books, student_id__in=student_ids)
        .order_by("column_id", "student_id", "-entered_at", "-id")
        .distinct("column_id", "student_id")
        .values_list(
            "column__gradebook_id", "student_id", "column__kind", "column__index", "value", "result"
        )
    )
    cells = {}
    for book, student, kind, index, value, result in entries:
        if value is not None or result is not None:
            cells.setdefault((book, student), {})[kind, index] = (
                value if value is not None else result
            )
    return cells


def carried_cells(term, subject, student_ids):
    """{student id: {(kind, index): value or result}}: the current carried results not cleared."""
    rows = (
        CarriedResult.objects.filter(term=term, subject=subject, student_id__in=student_ids)
        .order_by("student_id", "kind", "index", "-id")
        .distinct("student_id", "kind", "index")
        .values_list("student_id", "kind", "index", "value", "result")
    )
    carried = {}
    for student, kind, index, value, result in rows:
        if value is not None or result is not None:
            carried.setdefault(student, {})[kind, index] = value if value is not None else result
    return carried


def first_semesters(gradebook, earlier_term, student_ids):
    """{student id: Average of their own semester 1 gradebook(s) of the subject}; a student with
    none is left out. Two gradebooks (a class change in that term) give `split`. `left` is not
    applied: that book's roster judges it by today, and a class change between the terms is no
    leaving."""
    books = {
        book.school_class_id: book
        for book in Gradebook.objects.filter(
            term=earlier_term, subject=gradebook.subject
        ).select_related("profile_version")
    }
    if not books:
        return {}
    classes_of = {}
    for student, klass in (
        during(earlier_term)
        .filter(student_id__in=student_ids, school_class_id__in=books)
        .values_list("student_id", "school_class_id")
    ):
        classes_of.setdefault(student, set()).add(klass)
    columns = {}
    for column in GradebookColumn.objects.filter(gradebook__in=books.values()):
        columns.setdefault(column.gradebook_id, []).append(column)
    cells = current_cells(books.values(), list(classes_of))
    carried = carried_cells(earlier_term, gradebook.subject, list(classes_of))
    assessment = gradebook.subject.assessment
    out = {}
    for student, classes in classes_of.items():
        book = books[min(classes)]
        out[student] = averages.semester(
            book.profile_version.rules,
            assessment,
            required(columns.get(book.pk, []), assessment),
            cells.get((book.pk, student), {}),
            carried.get(student, {}),
            book.status,
            split=len(classes) > 1,
        )
    return out


def shown(average):
    if average is None:
        return None
    return {**asdict(average), "missing": [{"kind": k, "index": i} for k, i in average.missing]}


def roster_averages(gradebook, student_ids, in_class):
    """{student id: {"semester": ..., "year": ... or None}} for the gradebook's rows."""
    term, subject, rules = gradebook.term, gradebook.subject, gradebook.profile_version.rules
    assessment = subject.assessment
    needed = required(gradebook.gradebookcolumn_set.all(), assessment)
    cells = current_cells([gradebook], student_ids)
    carried = carried_cells(term, subject, student_ids)
    split = set(
        during(term)
        .filter(student_id__in=student_ids)
        .exclude(school_class_id=gradebook.school_class_id)
        .filter(
            school_class_id__in=Gradebook.objects.filter(term=term, subject=subject).values(
                "school_class_id"
            )
        )
        .values_list("student_id", flat=True)
    )
    terms_in_year, earlier_terms = term_position(term)
    first = {}
    if terms_in_year == 2 and earlier_terms == 1 and assessment == Subject.Assessment.SCORED:
        earlier = Term.objects.filter(
            school_year_id=term.school_year_id, ends_on__lt=term.starts_on
        ).get()
        first = first_semesters(gradebook, earlier, student_ids)
    out = {}
    for pk in student_ids:
        own_carried = carried.get(pk, {})
        semester = averages.semester(
            rules,
            assessment,
            needed,
            cells.get((gradebook.pk, pk), {}),
            own_carried,
            gradebook.status,
            left=pk not in in_class,
            split=pk in split,
        )
        year = averages.year(
            rules,
            assessment,
            terms_in_year,
            earlier_terms,
            first.get(pk),
            own_carried.get((PREVIOUS, 1)),
            semester,
        )
        out[pk] = {"semester": shown(semester), "year": shown(year)}
    return out
