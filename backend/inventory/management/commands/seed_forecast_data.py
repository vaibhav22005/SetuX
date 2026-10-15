from django.core.management.base import BaseCommand, CommandError

from inventory.models import Hospital
from inventory.services import BLOOD_GROUPS, save_synthetic_inventory_history


class Command(BaseCommand):
    help = "Generate synthetic daily inventory history for forecasting."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Number of daily records to generate per blood group (1-730).",
        )
        parser.add_argument(
            "--baseline-units",
            type=int,
            default=36,
            help="Baseline stock level used by the synthetic generator.",
        )
        parser.add_argument(
            "--hospital-id",
            type=int,
            help="Generate data only for this active hospital.",
        )

    def handle(self, *args, **options):
        days = options["days"]
        baseline_units = options["baseline_units"]
        if not 1 <= days <= 730:
            raise CommandError("--days must be between 1 and 730.")
        if baseline_units < 0:
            raise CommandError("--baseline-units cannot be negative.")

        hospitals_query = Hospital.objects.filter(is_active=True)
        if options["hospital_id"] is not None:
            hospitals_query = hospitals_query.filter(pk=options["hospital_id"])
            if not hospitals_query.exists():
                raise CommandError("No active hospital found with that ID.")
        hospitals = list(hospitals_query)
        if not hospitals:
            hospital, _ = Hospital.objects.get_or_create(
                registration_id="REG-001",
                defaults={
                    "name": "Pune Regional Blood Center",
                    "address": "Near Alandi Road, Pune",
                    "city": "Pune",
                    "latitude": 18.5204,
                    "longitude": 73.8567,
                    "is_active": True,
                },
            )
            if not hospital.is_active:
                raise CommandError("The demo hospital REG-001 exists but is inactive.")
            hospitals = [hospital]

        created_total = 0
        for hospital in hospitals:
            for blood_group in BLOOD_GROUPS:
                created_total += save_synthetic_inventory_history(
                    hospital,
                    blood_group=blood_group,
                    days=days,
                    baseline_units=baseline_units,
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Generated {created_total} synthetic inventory records across {len(hospitals)} "
                f"hospital(s) for {days} day(s). These records are simulated, not real stock data."
            )
        )
