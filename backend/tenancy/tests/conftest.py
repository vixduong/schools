import pytest

from tenancy.models import Probe, School
from tenancy.rls import school_scope


@pytest.fixture
def schools(transactional_db):
    """School A with two probes, School B with one. Committed, so other connections see them."""
    a = School.objects.create(name="A", subdomain="a")
    b = School.objects.create(name="B", subdomain="b")
    for school, names in ((a, ["a1", "a2"]), (b, ["b1"])):
        with school_scope(school.pk):
            Probe.objects.bulk_create([Probe(school=school, name=n) for n in names])
    return a, b
