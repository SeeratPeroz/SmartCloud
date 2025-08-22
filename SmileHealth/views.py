from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Patient, Image, Message,Profile,Video,Comment, Model3D
from .models import Profile  # Your profile model
from django.contrib.auth import authenticate, login as auth_login, logout
from django.contrib import messages
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
from django.contrib.auth import update_session_auth_hash
from django.http import HttpResponseForbidden
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.conf import settings
from django.core.mail import EmailMessage




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
    users = User.objects.exclude(id=request.user.id)  # for your chat list
    avatar = Profile.objects.filter(user=request.user).first()

    scope = request.GET.get('scope', 'all')  # 'all' | 'mine' | 'shared'

    if scope == 'mine':
        patients = Patient.objects.filter(usrID=request.user)
    elif scope == 'shared':
        patients = Patient.objects.filter(shared_with=request.user).exclude(usrID=request.user).distinct()
    else:  # 'all' -> show EVERYTHING in the DB, regardless of owner/share
        patients = Patient.objects.all()

    counts = {
        'all': Patient.objects.count(),
        'mine': Patient.objects.filter(usrID=request.user).count(),
        'shared': Patient.objects.filter(shared_with=request.user).exclude(usrID=request.user).distinct().count(),
    }

    return render(request, 'index.html', {
        'users': users,
        'patients': patients,
        'avatar': avatar,
        'scope': scope,
        'counts': counts,
    })

# Patient management view
@login_required
def patient_manage(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    users = User.objects.exclude(id=request.user.id)  # for share multiselect

    if request.method == "POST":
        form_type = request.POST.get("form")

        # Only owner can modify anything
        if patient.usrID != request.user:
            messages.error(request, "Nur der Eigentümer darf diesen Patienten bearbeiten oder teilen.")
            return redirect('patient_manage', patient_id=patient.id)

        if form_type == "details":
            patient.ptnName = request.POST.get("ptnName", patient.ptnName).strip()
            patient.ptnLastname = request.POST.get("ptnLastname", patient.ptnLastname).strip()
            patient.ptnDOB = request.POST.get("ptnDOB") or patient.ptnDOB
            patient.save()
            messages.success(request, "Patientendaten gespeichert.")
            return redirect('patient_manage', patient_id=patient.id)

        elif form_type == "share":
            ids = request.POST.getlist("share_with")
            share_set = User.objects.filter(id__in=ids).exclude(id=patient.usrID_id)
            patient.shared_with.set(share_set)
            messages.success(request, "Freigaben aktualisiert.")
            return redirect('patient_manage', patient_id=patient.id)

        elif form_type == "thumb":
            if 'thumbnail' in request.FILES:
                # Optional: validate size/type here
                patient.thumbnail = request.FILES['thumbnail']
                patient.save()
                messages.success(request, "Thumbnail aktualisiert.")
            else:
                messages.error(request, "Keine Bilddatei ausgewählt.")
            return redirect('patient_manage', patient_id=patient.id)

        elif form_type == "thumb_remove":
            if patient.thumbnail:
                patient.thumbnail.delete(save=False)
                patient.thumbnail = None
                patient.save()
                messages.success(request, "Thumbnail entfernt.")
            return redirect('patient_manage', patient_id=patient.id)

    # GET
    return render(request, 'patient_manage.html', {
        'patient': patient,
        'users': users,
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



def _can_access_patient(user, patient):
    return (patient.usrID_id == user.id) or patient.shared_with.filter(id=user.id).exists()


# Show patient info and all images
@login_required
def patient_image(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    # Fetch related 3D models
    models3d = Model3D.objects.filter(ptnID=patient).order_by('-id')
    images = Image.objects.filter(ptnID=patient)
    videos = patient.videos.all().order_by('-uploaded_at')  # NEW
    comments = Comment.objects.filter(patient=patient).select_related('author', 'author__profile')
    return render(request, 'patientImage.html', {'patient': patient, 'images': images, 'videos': videos, 'comments': comments,
    'can_comment': _can_access_patient(request.user, patient),
    'models3d': models3d
})

@require_POST
@login_required
# Adding comment to Patients 
def add_comment(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_access_patient(request.user, patient):
        return JsonResponse({'ok': False, 'error': 'Kein Zugriff'}, status=403)

    content = (request.POST.get('content') or '').strip()
    if not content:
        return JsonResponse({'ok': False, 'error': 'Kommentar darf nicht leer sein.'}, status=400)
    if len(content) > 2000:
        return JsonResponse({'ok': False, 'error': 'Max. 2000 Zeichen.'}, status=400)

    c = Comment.objects.create(patient=patient, author=request.user, content=content)
    return JsonResponse({
        'ok': True,
        'id': c.id,
        'content': c.content,
        'author': request.user.get_full_name() or request.user.username,
        'created': c.created_at.strftime('%Y-%m-%d %H:%M'),
    })


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


# Video Upload

@login_required
def upload_videos(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id, usrID=request.user)
    if request.method == 'POST' and request.FILES.getlist('videos'):
        for f in request.FILES.getlist('videos'):
            Video.objects.create(ptnID=patient, usrID=request.user, file=f, vidDesc='')
    return redirect('patientImage', patient_id=patient.id)

@login_required
def delete_videos(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id, usrID=request.user)
    if request.method == 'POST':
        ids = request.POST.getlist('selected_videos')
        Video.objects.filter(id__in=ids, ptnID=patient, usrID=request.user).delete()
    return redirect('patientImage', patient_id=patient.id)

@login_required
def delete_single_video(request, video_id):
    video = get_object_or_404(Video, id=video_id, usrID=request.user)
    pid = video.ptnID.id
    video.delete()
    return redirect('patientImage', patient_id=pid)




# 3D Model Upload
@login_required
@require_POST
def upload_models(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    files = request.FILES.getlist('models')
    # An optional single thumbnail per file can be sent as 'thumb' (client-side generated)
    # but to keep it simple we accept none and show a placeholder; you can add later.

    for f in files:
        name = (f.name or '').lower()
        ctype = (f.content_type or '').lower()
        if not (name.endswith('.stl') or 'model/stl' in ctype or 'application/sla' in ctype):
            continue  # skip non-stl silently
        Model3D.objects.create(ptnID=patient, usrID=request.user, file=f)

    return redirect('patientImage', patient_id=patient.id)

@login_required
@require_POST
def delete_models(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    ids = request.POST.getlist('selected_models')
    Model3D.objects.filter(ptnID=patient, id__in=ids, usrID=request.user).delete()
    return redirect('patientImage', patient_id=patient_id)

@login_required
def delete_single_model(request, model_id):
    m = get_object_or_404(Model3D, id=model_id, usrID=request.user)
    pid = m.ptnID.id
    m.delete()
    return redirect('patientImage', patient_id=pid)


# Feedback submission
@login_required
@require_POST
def send_feedback(request):
    fb_type  = request.POST.get('type', 'Other')
    subject  = request.POST.get('subject', 'Website-Feedback')
    message  = (request.POST.get('message') or '').strip()
    page_url = request.POST.get('page_url') or request.META.get('HTTP_REFERER', '')

    if not message:
        return JsonResponse({'ok': False, 'error': 'Nachricht darf nicht leer sein.'}, status=400)

    user = request.user
    who  = user.get_full_name() or user.username
    body = (
        f"Feedback-Typ: {fb_type}\n"
        f"Von: {who} (id={user.id}, username={user.username}, email={user.email})\n"
        f"Seite: {page_url}\n\n"
        f"Inhalt:\n{message}\n"
    )

    email = EmailMessage(
        subject=f"[CleverImplant] {subject}",
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=["software-feedback@dens-health-management.com"],
        reply_to=[user.email] if user.email else None,
    )

    # Attach up to 5 images ≤10MB each
    for f in request.FILES.getlist('attachments')[:5]:
        if f.content_type.startswith('image/') and f.size <= 10 * 1024 * 1024:
            email.attach(f.name, f.read(), f.content_type)

    email.send(fail_silently=False)
    return JsonResponse({'ok': True})