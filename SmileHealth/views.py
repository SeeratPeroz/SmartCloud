from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Patient, Image, Message,Profile
from .models import Profile  # Your profile model
from django.contrib.auth import authenticate, login as auth_login, logout
from django.contrib import messages
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
from django.contrib.auth import update_session_auth_hash



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
            #int("User authenticated successfully")
            return redirect('index')
        else:
            #rint("User authentication failed")
            messages.error(request, "Ungültiger Benutzername oder Passwort")

    return render(request, "login.html")

def logout_view(request):
    logout(request)
    return redirect('login')


# Main patient list
@login_required
def index(request):
    users = User.objects.exclude(id=request.user.id)  # Exclude yourself
    avatar = Profile.objects.filter(user=request.user).first()
    patients = Patient.objects.all()
    return render(request, 'index.html', {
        'users': users,
        'patients': patients,
        'avatar': avatar,
    })

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



@login_required
# Delete a patient
def delete_patient(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    # Add any permission checks here
    patient.delete()
    return redirect('index')



@login_required
def get_unread_message_count(request):
    count = Message.objects.filter(receiver=request.user, is_read=False).count()
    return JsonResponse({'unread_count': count})



@login_required
def user_settings(request):
    avatar_nums = range(1, 15)  # 1 to 10
    user = request.user
    # Ensure user has a profile (create if missing)
    profile, created = Profile.objects.get_or_create(user=user)
    
    if request.method == "POST":
        profile = user.profile

        # Basic info
        user.username = request.POST.get("username")
        user.first_name = request.POST.get("first_name")
        user.last_name = request.POST.get("last_name")
        user.email = request.POST.get("email")

        # Avatar from online source
        profile.avatar_url = request.POST.get("avatar_url")
        profile.save()

        # Change password
        password = request.POST.get("password")
        if password:
            user.set_password(password)
            update_session_auth_hash(request, user)

        user.save()
        messages.success(request, "Profil erfolgreich aktualisiert!")
        return redirect("user_settings")

    return render(request, "user_settings.html", {"avatar_nums": avatar_nums})