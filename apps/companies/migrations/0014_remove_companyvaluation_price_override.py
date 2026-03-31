from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0013_add_key_questions'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='companyvaluation',
            name='price_override',
        ),
    ]
