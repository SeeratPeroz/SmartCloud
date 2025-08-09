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
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    avatar_url = models.URLField(default="https://i.pravatar.cc/150?img=1")  # default avatar

    def __str__(self):
        return self.user.username
    