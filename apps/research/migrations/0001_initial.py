import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('companies', '0013_add_key_questions'),
        ('organizations', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ResearchProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('ir_url', models.URLField(blank=True, help_text='Investor Relations page URL (auto-detected or manual)')),
                ('ceo_name', models.CharField(blank=True, max_length=255)),
                ('cfo_name', models.CharField(blank=True, max_length=255)),
                ('other_executives', models.TextField(blank=True, help_text='Other executives to search for, one per line')),
                ('extra_search_terms', models.TextField(blank=True, help_text='Additional search terms for YouTube/podcast, one per line')),
                ('exclude_domains', models.TextField(blank=True, help_text='Domains to skip when scraping, one per line')),
                ('company', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='research_profile', to='companies.company')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'research_profiles',
            },
        ),
        migrations.CreateModel(
            name='ResearchJob',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('generated', 'Prompt Generated'), ('in_progress', 'In Progress'), ('completed', 'Completed'), ('failed', 'Failed')], default='generated', max_length=20)),
                ('prompt_text', models.TextField(help_text='The Claude Code prompt that was generated')),
                ('config_snapshot', models.JSONField(default=dict, help_text='Snapshot of ResearchProfile fields at generation time')),
                ('notebook_url', models.URLField(blank=True, help_text='NotebookLM or Drive folder URL')),
                ('files_found', models.PositiveIntegerField(default=0, help_text='Number of documents found')),
                ('videos_found', models.PositiveIntegerField(default=0, help_text='Number of videos found')),
                ('notes_text', models.TextField(blank=True, help_text='Freeform notes about the run')),
                ('started_at', models.DateTimeField(blank=True, null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='research_jobs', to='companies.company')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='%(app_label)s_%(class)s', to='organizations.organization')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_created', to=settings.AUTH_USER_MODEL)),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_updated', to=settings.AUTH_USER_MODEL)),
                ('deleted_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='%(app_label)s_%(class)s_deleted', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'research_jobs',
                'ordering': ['-created_at'],
            },
        ),
    ]
