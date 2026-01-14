# Generated manually for company category restructure

from django.db import migrations, models


def migrate_portfolio_to_long_book(apps, schema_editor):
    """Migrate existing 'portfolio' companies to 'long_book'."""
    Company = apps.get_model('companies', 'Company')
    Company.objects.filter(status='portfolio').update(status='long_book')


def reverse_long_book_to_portfolio(apps, schema_editor):
    """Reverse migration: long_book back to portfolio."""
    Company = apps.get_model('companies', 'Company')
    Company.objects.filter(status='long_book').update(status='portfolio')


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0010_make_shares_outstanding_optional'),
    ]

    operations = [
        # 1. Add direction field
        migrations.AddField(
            model_name='company',
            name='direction',
            field=models.CharField(
                blank=True,
                null=True,
                max_length=10,
                choices=[('long', 'Long'), ('short', 'Short')],
                db_index=True,
                help_text='Direction for On Deck companies (Long or Short)',
            ),
        ),

        # 2. Rename alert_price to alert_price_low
        migrations.RenameField(
            model_name='company',
            old_name='alert_price',
            new_name='alert_price_low',
        ),

        # 3. Rename alert_price_reason to alert_reason
        migrations.RenameField(
            model_name='company',
            old_name='alert_price_reason',
            new_name='alert_reason',
        ),

        # 4. Add alert_price_high field
        migrations.AddField(
            model_name='company',
            name='alert_price_high',
            field=models.DecimalField(
                blank=True,
                null=True,
                max_digits=12,
                decimal_places=2,
                help_text='High price alert - triggers when price rises to this level (short opportunity)',
            ),
        ),

        # 5. Migrate portfolio -> long_book
        migrations.RunPython(
            migrate_portfolio_to_long_book,
            reverse_long_book_to_portfolio,
        ),

        # 6. Add index on (organization, direction)
        migrations.AddIndex(
            model_name='company',
            index=models.Index(fields=['organization', 'direction'], name='companies_c_organiz_d5f8e2_idx'),
        ),
    ]
