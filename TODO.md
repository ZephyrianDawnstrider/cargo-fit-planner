# TODO for Converting Streamlit App to Django

## Completed
- [x] Update requirements.txt (remove streamlit, flask; add django)
- [x] Install dependencies (pip install -r requirements.txt) - Note: ortools failed due to timeout, may need retry
- [x] Create Django project (django-admin startproject dcd_project .)
- [x] Create Django app (python manage.py startapp optimization)
- [x] Move core functions to optimization/utils.py
- [x] Create optimization/forms.py for upload form
- [x] Create optimization/views.py for handling upload and results
- [x] Create templates: upload.html and results.html
- [x] Update dcd_project/settings.py: add app to INSTALLED_APPS, update ALLOWED_HOSTS
- [x] Create optimization/urls.py
- [x] Update dcd_project/urls.py to include app URLs
- [x] Retry installing ortools (pip install ortools) - running
- [x] Run migrations (python manage.py makemigrations, python manage.py migrate) - failed due to missing ortools

## Pending
- [ ] Wait for ortools installation to complete
- [ ] Run migrations again after ortools is installed
- [ ] Run the server (python manage.py runserver)
- [ ] Test the app by uploading a file and generating the report
- [ ] Ensure all functions work correctly in Django context
- [ ] Handle any errors or missing dependencies
