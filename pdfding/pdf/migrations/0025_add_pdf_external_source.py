from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pdf', '0024_remove_unneeded_null_true'),
    ]

    operations = [
        migrations.AddField(
            model_name='pdf',
            name='external_source',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name='pdf',
            name='external_id',
            field=models.CharField(blank=True, db_index=True, default='', max_length=255),
        ),
        migrations.AddField(
            model_name='pdf',
            name='external_modified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pdf',
            name='external_url',
            field=models.URLField(blank=True, default='', max_length=500),
        ),
    ]
