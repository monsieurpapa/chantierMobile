import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0003_budget_unique_id_expense_unique_id_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='expense',
            name='expense_date',
            field=models.DateField(
                default=datetime.date.today,
                help_text='Date the expense was incurred (used for budget period matching)',
            ),
            preserve_default=False,
        ),
    ]
