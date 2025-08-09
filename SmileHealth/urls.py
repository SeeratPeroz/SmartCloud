from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('', views.login, name='login'),       # login page
    path('logout/', views.logout_view, name='logout'),
    path('index/', views.index, name='index'),  # main page



    path('load_new_fall/', views.load_new_fall, name='load_new_fall'),
    path('patients/', views.patient_list, name='patient_list'),
    path('add_patient/', views.add_patient, name='add_patient'),

    # Patient image page
    path('patient/<int:patient_id>/', views.patient_image, name='patientImage'),

    # Upload & delete images for patient
    path('patient/<int:patient_id>/upload/', views.upload_images, name='upload_images'),
    path('patient/<int:patient_id>/delete/', views.delete_images, name='delete_images'),
    path('image/<int:image_id>/delete/', views.delete_single_image, name='delete_single_image'),


    path('delete_patient/<int:patient_id>/', views.delete_patient, name='delete_patient'),


    # Profile management
    path('settings/', views.user_settings, name='user_settings')

]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)