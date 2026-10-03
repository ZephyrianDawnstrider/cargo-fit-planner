param([int]$Port = 8762)
$ErrorActionPreference = 'Stop'
$env:DJANGO_SETTINGS_MODULE = 'dcd_project.settings_demo'
$env:PYTHONDONTWRITEBYTECODE = '1'
python -B manage.py runserver "127.0.0.1:$Port" --noreload
