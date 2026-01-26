# Generated migration for refactoring MaterialRequest to support multiple materials

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('materials', '0003_material_unique_id_materialrequest_unique_id'),
    ]

    operations = [
        # Add new fields to MaterialRequest
        migrations.AddField(
            model_name='materialrequest',
            name='notes',
            field=models.TextField(blank=True, help_text='Additional notes or instructions for this request', null=True),
        ),
        
        # Create MaterialRequestItem model
        migrations.CreateModel(
            name='MaterialRequestItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('unique_id', models.CharField(editable=False, max_length=36, null=True, unique=True)),
                ('quantity', models.DecimalField(decimal_places=2, max_digits=10)),
                ('notes', models.TextField(blank=True, help_text='Notes specific to this material item', null=True)),
                ('material', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='request_items', to='materials.material')),
                ('request', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='materials.materialrequest')),
            ],
            options={
                'verbose_name': 'Material Request Item',
                'verbose_name_plural': 'Material Request Items',
            },
        ),
        
        # Add unique together constraint
        migrations.AlterUniqueTogether(
            name='materialrequestitem',
            unique_together={('request', 'material')},
        ),
    ]
