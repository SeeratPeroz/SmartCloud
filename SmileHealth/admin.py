from django.contrib import admin
from .models import Patient, Image

# Register your models here.
from django.contrib import admin
from .models import Patient, Image

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ('id', 'ptnName', 'ptnLastname', 'ptnDOB', 'usrID')
    search_fields = ('ptnName', 'ptnLastname')
    list_filter = ('usrID',)

@admin.register(Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'imgDesc', 'ptnID', 'usrID')
    search_fields = ('imgDesc',)
    list_filter = ('ptnID', 'usrID')
