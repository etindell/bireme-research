# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0006_add_business_summary'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='ai_summary',
            field=models.TextField(blank=True, help_text='AI-generated summary of research notes'),
        ),
        migrations.AddField(
            model_name='company',
            name='summary_updated_at',
            field=models.DateTimeField(blank=True, help_text='When the AI summary was last generated', null=True),
        ),
    ]
