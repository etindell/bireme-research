"""Link task templates to survey templates, rename quarterly tasks, create missing task templates."""
from django.db import migrations


# Mapping: (task template title prefix, survey slug)
# For quarterly tasks, prefix matches all 4 quarters
RENAME_MAP = {
    'Code of Ethics: Quarterly transactions report': 'Quarterly access person certification and transaction report',
}

LINK_MAP = [
    # (task title contains, survey slug)
    ('Quarterly access person certification and transaction report', 'quarterly-access-person-certification'),
    ('BCP drill + cybersecurity tabletop', 'annual-cybersecurity-communications-attestation'),
]

# New task templates for surveys that don't have a corresponding task template
NEW_TASK_TEMPLATES = [
    {
        'title': 'Annual holdings and accounts report',
        'description': 'Collect annual holdings and accounts disclosures from access persons.',
        'frequency': 'ANNUAL',
        'default_due_month': 1,
        'default_due_day': 31,
        'tags': 'annual,code-of-ethics,access-person',
        'owner_role': 'CCO',
        'suggested_evidence': 'Completed survey responses; holdings attestation.',
        'survey_slug': 'annual-holdings-and-accounts-report',
    },
    {
        'title': 'Annual Code of Ethics and Compliance Manual attestation',
        'description': 'Annual attestation confirming receipt and understanding of Code of Ethics and Compliance Manual.',
        'frequency': 'ANNUAL',
        'default_due_month': 1,
        'default_due_day': 31,
        'tags': 'annual,code-of-ethics,attestation',
        'owner_role': 'CCO',
        'suggested_evidence': 'Completed attestation survey responses.',
        'survey_slug': 'annual-code-of-ethics-and-compliance-manual-attestation',
    },
    {
        'title': 'Annual OBA / Conflicts / Political Contributions survey',
        'description': 'Annual survey on outside business activities, conflicts of interest, and political contributions.',
        'frequency': 'ANNUAL',
        'default_due_month': 1,
        'default_due_day': 31,
        'tags': 'annual,oba,conflicts',
        'owner_role': 'CCO',
        'suggested_evidence': 'Completed survey responses; exception follow-ups.',
        'survey_slug': 'annual-oba-conflicts-political-contributions-survey',
    },
]


def link_templates(apps, schema_editor):
    ComplianceTaskTemplate = apps.get_model('compliance', 'ComplianceTaskTemplate')
    ComplianceTask = apps.get_model('compliance', 'ComplianceTask')
    SurveyTemplate = apps.get_model('compliance', 'SurveyTemplate')

    for org_id in set(
        ComplianceTaskTemplate.objects.values_list('organization_id', flat=True).distinct()
    ) | set(
        SurveyTemplate.objects.values_list('organization_id', flat=True).distinct()
    ):
        # 1. Rename quarterly task templates and their instances
        for old_prefix, new_prefix in RENAME_MAP.items():
            for q in range(1, 5):
                old_title = f'{old_prefix} (Q{q})'
                new_title = f'{new_prefix} (Q{q})'
                tpl = ComplianceTaskTemplate.objects.filter(
                    organization_id=org_id, title=old_title, is_deleted=False,
                ).first()
                if tpl:
                    tpl.title = new_title
                    tpl.save(update_fields=['title'])
                    # Update existing task instances
                    ComplianceTask.objects.filter(
                        template=tpl, organization_id=org_id,
                    ).update(title=new_title)

        # 2. Link existing task templates to survey templates
        for title_contains, survey_slug in LINK_MAP:
            survey = SurveyTemplate.objects.filter(
                organization_id=org_id, slug=survey_slug,
            ).first()
            if survey:
                ComplianceTaskTemplate.objects.filter(
                    organization_id=org_id,
                    title__icontains=title_contains,
                    is_deleted=False,
                ).update(survey_template=survey)

        # 3. Create new task templates for surveys without one
        for entry in NEW_TASK_TEMPLATES:
            survey = SurveyTemplate.objects.filter(
                organization_id=org_id, slug=entry['survey_slug'],
            ).first()
            if not survey:
                continue
            # Don't create if already exists
            if ComplianceTaskTemplate.objects.filter(
                organization_id=org_id, title=entry['title'], is_deleted=False,
            ).exists():
                continue
            ComplianceTaskTemplate.objects.create(
                organization_id=org_id,
                title=entry['title'],
                description=entry['description'],
                frequency=entry['frequency'],
                default_due_month=entry.get('default_due_month'),
                default_due_day=entry.get('default_due_day'),
                tags=entry.get('tags', ''),
                owner_role=entry.get('owner_role', ''),
                suggested_evidence=entry.get('suggested_evidence', ''),
                survey_template=survey,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("compliance", "0007_add_survey_template_to_task_template"),
    ]

    operations = [
        migrations.RunPython(link_templates, migrations.RunPython.noop),
    ]
