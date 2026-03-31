from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('todos', '0008_migrate_existing_todos_to_personal'),
    ]

    operations = [
        migrations.AddField(
            model_name='todo',
            name='google_task_id',
            field=models.CharField(
                blank=True,
                help_text='Google Tasks ID for deduplication during sync',
                max_length=255,
                null=True,
                unique=True,
            ),
        ),
        migrations.CreateModel(
            name='GoogleTasksSyncState',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('last_synced_at', models.DateTimeField()),
                ('user', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='google_tasks_sync_state',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'google_tasks_sync_state',
            },
        ),
    ]
