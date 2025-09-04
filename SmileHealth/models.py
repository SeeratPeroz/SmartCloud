from django.db import models
from django.contrib.auth.models import User
from django.utils.text import slugify
from django.db.models import Q

class Branch(models.Model):
    name = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:220]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class PatientQuerySet(models.QuerySet):
    def visible_to(self, user):
        if not user.is_authenticated:
            return self.none()

        # Admins see everything
        if user.is_superuser or user.is_staff:
            return self

        # Owner always sees; PUBLIC_ORG visible to all; SHARED visible to selected users
        return self.filter(
            Q(usrID=user)
            | Q(visibility=Patient.Visibility.PUBLIC_ORG)
            | (Q(visibility=Patient.Visibility.SHARED) & Q(shared_with=user))
        ).distinct()


class PatientManager(models.Manager):
    def get_queryset(self):
        return PatientQuerySet(self.model, using=self._db)

    def visible_to(self, user):
        return self.get_queryset().visible_to(user)

class Patient(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE = "PRIVATE", "Privat"                      # owner (+ admins)
        SHARED = "SHARED", "Geteilt (ausgewählte Nutzer)"  # owner + shared_with (+ admins)
        PUBLIC_ORG = "PUBLIC_ORG", "Öffentlich (Organisation)"  # alle eingeloggten Nutzer (+ admins)

    ptnName = models.CharField(max_length=100)
    ptnLastname = models.CharField(max_length=100)
    ptnDOB = models.DateField()
    usrID = models.ForeignKey(User, on_delete=models.CASCADE, related_name='patients')
    thumbnail = models.ImageField(upload_to='patient_thumbs/', blank=True, null=True)
    shared_with = models.ManyToManyField(User, related_name='shared_patients', blank=True)

    # DEFAULT CHANGED: new patients are Öffentlich
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PUBLIC_ORG,  # was PRIVATE
        db_index=True,
    )

    objects = PatientManager()  # <-- attach the custom manager

    def __str__(self):
        return f"{self.ptnName} {self.ptnLastname}"

# Image model for patient images
class Image(models.Model):
    imgDesc = models.TextField(blank=True)
    image = models.ImageField(upload_to='patient_images/')
    ptnID = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='images')
    usrID = models.ForeignKey(User, on_delete=models.CASCADE, related_name='images')

    def __str__(self):
        return f"Image {self.id} for {self.ptnID}"

# Message model for user communication
class Message(models.Model):
    sender = models.ForeignKey(User, related_name='sent_messages', on_delete=models.CASCADE)
    receiver = models.ForeignKey(User, related_name='received_messages', on_delete=models.CASCADE)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"From {self.sender} to {self.receiver} at {self.timestamp}"
    
# Profile model for user settings
class Profile(models.Model):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        MANAGER = "MANAGER", "Manager"
        DOCTOR = "DOCTOR", "Doctor"
        ASSISTANT = "ASSISTANT", "Assistant"
        VIEWER = "VIEWER", "Viewer"
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    avatar_url = models.URLField(default="https://i.pravatar.cc/150?img=1")  # default avatar

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.VIEWER,
        db_index=True,
    )
    branches = models.ManyToManyField(Branch, blank=True, related_name="users")

    def __str__(self):
        return self.user.username
    

# Viedeo Upload
class Video(models.Model):
    vidDesc = models.TextField(blank=True)
    file = models.FileField(upload_to='patient_videos/')  # saved at MEDIA_ROOT/patient_videos/<filename>
    ptnID = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='videos')
    usrID = models.ForeignKey(User, on_delete=models.CASCADE, related_name='videos')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Video {self.id} for {self.ptnID}"

# place near your other models
class Comment(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='patient_comments')
    content = models.TextField(max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Comment by {self.author} on {self.patient} at {self.created_at:%Y-%m-%d %H:%M}"

# 3D Model for Patients
class Model3D(models.Model):
    ptnID = models.ForeignKey('Patient', on_delete=models.CASCADE, related_name='models3d')
    usrID = models.ForeignKey(User, on_delete=models.CASCADE, related_name='models3d')
    file = models.FileField(upload_to='patient_models/')                 # .stl
    thumbnail = models.ImageField(upload_to='patient_models/thumbs/', blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"3D Model {self.id} for {self.ptnID}"
