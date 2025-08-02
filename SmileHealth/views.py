from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Patient, Image
from django.contrib.auth import authenticate, login as auth_login, logout
from django.contrib import messages

# Home redirects to index
def home(request):
    return index(request)
def login(request):
    if request.user.is_authenticated:
        return redirect('index')  # Already logged in

    if request.method == "POST":
        username = request.POST.get("username")  # ✅ use "username" field
        password = request.POST.get("password")
        
        user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            print("User authenticated successfully")
            return redirect('index')
        else:
            print("User authentication failed")
            messages.error(request, "Invalid username or password")

    return render(request, "login.html")

def logout_view(request):
    logout(request)
    return redirect('login')


# Main patient list
@login_required
def index(request):
    patients = Patient.objects.all()
    return render(request, 'index.html', {'patients': patients})

# Page for loading new fall (case)
@login_required
def load_new_fall(request):
    return render(request, 'newFall.html')

# Patient list again (optional if index handles it)
@login_required
def patient_list(request):
    patients = Patient.objects.all()
    return render(request, 'index.html', {'patients': patients})

# Add a new patient (from form)
@login_required
def add_patient(request):
    if request.method == "POST":
        ptnName = request.POST.get('ptnName')
        ptnLastname = request.POST.get('ptnLastname')
        ptnDOB = request.POST.get('ptnDOB')

        Patient.objects.create(
            ptnName=ptnName,
            ptnLastname=ptnLastname,
            ptnDOB=ptnDOB,
            usrID=request.user
        )
        return redirect('index')

    return redirect('index')

# Show patient info and all images
@login_required
def patient_image(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    images = Image.objects.filter(ptnID=patient)
    return render(request, 'patientImage.html', {'patient': patient, 'images': images})

# Upload multiple images
@login_required
def upload_images(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if request.method == 'POST' and request.FILES.getlist('images'):
        for file in request.FILES.getlist('images'):
            Image.objects.create(
                ptnID=patient,
                usrID=request.user,
                image=file,
                imgDesc=''  # or set from request.POST if needed
            )
    return redirect('patientImage', patient_id=patient.id)

# Delete selected images
@login_required
def delete_images(request, patient_id):
    if request.method == 'POST':
        image_ids = request.POST.getlist('selected_images')
        Image.objects.filter(id__in=image_ids, usrID=request.user).delete()
    return redirect('patientImage', patient_id=patient_id)

# Delete one image
@login_required
def delete_single_image(request, image_id):
    image = get_object_or_404(Image, id=image_id, usrID=request.user)
    patient_id = image.ptnID.id
    image.delete()
    return redirect('patientImage', patient_id=patient_id)
