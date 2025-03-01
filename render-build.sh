#!/bin/bash
pip install -r requirements.txt
python manage.py migrate --no-input
python manage.py createsuperuser --no-input || true
python manage.py collectstatic --no-input

