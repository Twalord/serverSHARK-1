# -*- coding: utf-8 -*-
# Generated by Django 1.9.7 on 2016-06-07 14:57
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('smartshark', '0004_auto_20160603_1549'),
    ]

    operations = [
        migrations.CreateModel(
            name='Argument',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('required', models.BooleanField()),
                ('position', models.IntegerField()),
                ('type', models.CharField(choices=[('install', 'Installation Argument'), ('execute', 'Execution Argument')], max_length=7)),
            ],
        ),
        migrations.CreateModel(
            name='Plugin',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('author', models.CharField(max_length=200)),
                ('version', models.CharField(max_length=50)),
                ('abstraction_level', models.CharField(choices=[('rev', 'Revision'), ('repo', 'Repository'), ('other', 'Other')], max_length=5)),
                ('definition', models.FileField(upload_to='uploads/')),
                ('schema', models.FileField(upload_to='uploads/')),
                ('active', models.BooleanField()),
                ('installed', models.BooleanField()),
                ('arguments', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='smartshark.Argument')),
                ('requires', models.ManyToManyField(related_name='_plugin_requires_+', to='smartshark.Plugin')),
            ],
        ),
        migrations.CreateModel(
            name='PluginExecution',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('added_at', models.DateTimeField(auto_now_add=True)),
                ('submission_value', models.CharField(blank=True, max_length=300)),
                ('status', models.CharField(choices=[('queue', 'In Queue'), ('running', 'Running'), ('finished', 'Finished'), ('error', 'Error')], max_length=8)),
                ('plugin', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='smartshark.Plugin')),
            ],
        ),
        migrations.AlterField(
            model_name='smartsharkuser',
            name='roles',
            field=models.ManyToManyField(blank=True, to='smartshark.MongoRole'),
        ),
    ]
