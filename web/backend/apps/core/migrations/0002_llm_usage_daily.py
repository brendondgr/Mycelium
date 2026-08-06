from django.db import migrations, models


class Migration(migrations.Migration):
    """The per-day LLM call/token ledger the nightly analytics report reads."""

    dependencies = [
        ('core', '0001_enable_pgvector'),
    ]

    operations = [
        migrations.CreateModel(
            name='LLMUsageDaily',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('day', models.DateField(db_index=True)),
                ('component', models.CharField(help_text="Which caller made the requests — 'papers', 'briefing', …", max_length=60)),
                ('calls', models.PositiveIntegerField(default=0)),
                ('failures', models.PositiveIntegerField(default=0, help_text='Calls that raised — an unreachable endpoint, a timeout, or a response the client could not parse.')),
                ('prompt_tokens', models.BigIntegerField(default=0)),
                ('completion_tokens', models.BigIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'LLM daily usage',
                'verbose_name_plural': 'LLM daily usage',
                'ordering': ['-day', 'component'],
                'constraints': [models.UniqueConstraint(fields=('day', 'component'), name='core_llm_usage_unique_day_component')],
            },
        ),
    ]
