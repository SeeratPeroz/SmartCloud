from django.contrib import admin
from .models import Patient, Image, Message, Profile, Comment, Model3D, Video

# Register your models here.
from django.contrib import admin
from .models import Patient, Image

admin.site.register(Message)
admin.site.register(Comment)
admin.site.register(Model3D)
admin.site.register(Video)


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

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'avatar_url')
    search_fields = ('user__username', 'user__email')

