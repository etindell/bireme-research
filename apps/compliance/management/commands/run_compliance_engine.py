from django.core.management.base import BaseCommand
from apps.organizations.models import Organization
from apps.compliance.services.compliance_engine import run_compliance_engine


class Command(BaseCommand):
    help = 'Run the compliance engine — check all triggers and create tasks for what needs doing'

    def add_arguments(self, parser):
        parser.add_argument('--org', type=str, help='Organization slug (all orgs if omitted)')

    def handle(self, *args, **options):
        orgs = Organization.objects.all()
        if options['org']:
            orgs = orgs.filter(slug=options['org'])

        for org in orgs:
            self.stdout.write(f'\n=== {org.name} ===')
            result = run_compliance_engine(org)

            if result.get('error'):
                self.stderr.write(f'  Error: {result["error"]}')
                continue

            summary = result['summary']
            self.stdout.write(f'  Tasks created: {summary["total"]}')
            if summary['form_adv']:
                self.stdout.write(f'    Form ADV: {summary["form_adv"]}')
            if summary['form_d']:
                self.stdout.write(f'    Form D: {summary["form_d"]}')
            if summary['blue_sky']:
                self.stdout.write(f'    Blue Sky: {summary["blue_sky"]}')
            if summary['aml_cft']:
                self.stdout.write(f'    AML/CFT: {summary["aml_cft"]}')

            for task in result['tasks_created']:
                self.stdout.write(f'    + {task.title} (due {task.due_date})')

        self.stdout.write(self.style.SUCCESS('\nDone.'))
