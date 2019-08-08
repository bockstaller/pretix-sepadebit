# Generated by Django 2.2 on 2019-04-29 08:11

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pretixbase', '0118_auto_20190423_0839'),
        ('pretix_sepadebit', '0004_sepaexport_testmode'),
    ]

    operations = [
        migrations.AddField(
            model_name='sepaexport',
            name='organizer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='sepa_exports', to='pretixbase.Organizer'),
        ),
        migrations.AlterField(
            model_name='sepaexport',
            name='event',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='sepa_exports', to='pretixbase.Event'),
        ),
        migrations.AddField(
            model_name='sepaexport',
            name='currency',
            field=models.CharField(blank=True, max_length=9),
        ),
    ]