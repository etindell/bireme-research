"""
Migrate priority choices: HIGH/MEDIUM/LOW/NONE → HIGH/NORMAL/TICKLER.

Mapping:
- high → high (unchanged)
- medium → normal
- low → tickler
- none → normal
- '' or NULL → normal
"""
from django.db import migrations, models


def migrate_priorities(apps, schema_editor):
    Todo = apps.get_model('todos', 'Todo')
    # medium/none/blank → normal
    Todo.objects.filter(priority__in=['medium', 'none', '']).update(priority='normal')
    Todo.objects.filter(priority__isnull=True).update(priority='normal')
    # low → tickler
    Todo.objects.filter(priority='low').update(priority='tickler')


class Migration(migrations.Migration):

    dependencies = [
        ('todos', '0009_todo_google_task_id_googletaskssyncstate'),
    ]

    operations = [
        migrations.RunPython(migrate_priorities, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='todo',
            name='priority',
            field=models.CharField(
                choices=[('high', 'High'), ('normal', 'Normal'), ('tickler', 'Tickler')],
                db_index=True,
                default='normal',
                max_length=10,
            ),
        ),
    ]
