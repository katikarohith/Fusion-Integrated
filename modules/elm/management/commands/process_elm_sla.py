from django.core.management.base import BaseCommand

from modules.elm.services.sla import process_sla_thresholds


class Command(BaseCommand):
    help = "Process ELM reminder and escalation thresholds for pending workflow tasks."

    def handle(self, *args, **options):
        result = process_sla_thresholds()
        self.stdout.write(
            self.style.SUCCESS(
                f"ELM SLA: {result['reminders']} reminder(s), {result['escalations']} escalation(s)"
            )
        )
