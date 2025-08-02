from django.db import models
from django.contrib.auth.models import User

class Patient(models.Model):
    ptnName = models.CharField(max_length=100)
    ptnLastname = models.CharField(max_length=100)
    ptnDOB = models.DateField()
    usrID = models.ForeignKey(User, on_delete=models.CASCADE, related_name='patients')

    def __str__(self):
        return f"{self.ptnName} {self.ptnLastname}"

class Image(models.Model):
    imgDesc = models.TextField(blank=True)
    image = models.ImageField(upload_to='patient_images/')
    ptnID = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name='images')
    usrID = models.ForeignKey(User, on_delete=models.CASCADE, related_name='images')

    def __str__(self):
        return f"Image {self.id} for {self.ptnID}"
