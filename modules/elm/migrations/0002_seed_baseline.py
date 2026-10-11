from decimal import Decimal

from django.db import migrations


LEAVE_TYPES = [
    ("CL", "Casual Leave"),
    ("RH", "Restricted Holiday"),
    ("SCL", "Special Casual Leave"),
    ("EL", "Earned Leave"),
    ("COL", "Commuted Leave"),
    ("VL", "Vacation Leave"),
]

# Baseline values from the supplied ELM business-rule specification.
# Authority routing and academic calendars are instance-specific and are not
# seeded here; a Leave Administrator must configure the current institution data.
POLICIES = [
    ("CL", "faculty", "8.00", False, None, "working", False, False),
    ("CL", "staff", "8.00", False, None, "working", False, False),
    ("RH", "faculty", "2.00", False, None, "restricted_holiday", False, False),
    ("RH", "staff", "2.00", False, None, "restricted_holiday", False, False),
    ("SCL", "faculty", "15.00", False, None, "working", False, False),
    ("SCL", "staff", "15.00", False, None, "working", False, False),
    ("EL", "faculty", "0.00", True, None, "continuous", False, False),
    ("EL", "staff", "30.00", True, None, "continuous", False, False),
    ("COL", "faculty", "20.00", True, None, "continuous", False, False),
    ("COL", "staff", "20.00", True, None, "continuous", False, False),
    ("VL", "faculty", "60.00", False, None, "continuous", False, True),
]


def seed_baseline(apps, schema_editor):
    LeaveType = apps.get_model("elm", "LeaveType")
    LeavePolicy = apps.get_model("elm", "LeavePolicy")
    for code, name in LEAVE_TYPES:
        leave_type, _ = LeaveType.objects.using(schema_editor.connection.alias).update_or_create(
            code=code,
            defaults={"name": name, "is_active": True},
        )
        for (policy_code, employee_kind, entitlement, carry, limit, mode,
             medical, vacation) in POLICIES:
            if policy_code != code:
                continue
            LeavePolicy.objects.using(schema_editor.connection.alias).update_or_create(
                leave_type_id=leave_type.pk,
                employee_kind=employee_kind,
                defaults={
                    "annual_entitlement": Decimal(entitlement),
                    "carry_forward": carry,
                    "carry_forward_limit": Decimal(limit) if limit is not None else None,
                    "counting_mode": mode,
                    "requires_medical_evidence": medical,
                    "requires_vacation_period": vacation,
                    "is_active": True,
                },
            )


def reverse_baseline(apps, schema_editor):
    # Do not delete administrator changes during a rollback.
    return None


class Migration(migrations.Migration):
    dependencies = [("elm", "0001_initial")]

    operations = [migrations.RunPython(seed_baseline, reverse_baseline)]
