from django.core.management.base import BaseCommand, CommandError

from modules.elm.services.year_end import process_year_end


class Command(BaseCommand):
    help = "Run idempotent ELM year-end entitlement processing."

    def add_arguments(self, parser):
        parser.add_argument("year", type=int)

    def handle(self, *args, **options):
        run = process_year_end(year=options["year"])
        self.stdout.write(
            self.style.SUCCESS(f"ELM year-end {run.year}: {run.status}; {run.summary}")
        )
        if run.status == "failed":
            raise CommandError("Year-end processing reported exceptions.")
