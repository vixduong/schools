from django.core.validators import RegexValidator
from django.db import models

# One DNS label: schools stay one level deep under the base domain (docs/tech-stack.md).
SUBDOMAIN_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"


class School(models.Model):
    """The tenant. Global table: no RLS, readable by the app role to resolve the host."""

    name = models.CharField(max_length=200)
    subdomain = models.CharField(
        max_length=63, unique=True, validators=[RegexValidator(SUBDOMAIN_PATTERN)]
    )

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(subdomain__regex=SUBDOMAIN_PATTERN),
                name="school_subdomain_is_dns_label",
            )
        ]

    def __str__(self):
        return self.name


class Probe(models.Model):
    """Minimal tenant-owned row that proves RLS end to end; replaced by real models later."""

    school = models.ForeignKey(School, on_delete=models.CASCADE)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name
