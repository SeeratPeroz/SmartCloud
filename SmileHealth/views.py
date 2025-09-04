from django.http import JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login as auth_login, logout, update_session_auth_hash
from django.contrib import messages
from django.contrib.auth.models import User
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.conf import settings
from django.urls import reverse
import os, uuid
from django.core.files.storage import default_storage


from .models import (
    Patient, Image, Message, Profile, Video, Comment, Model3D
)

# ---------- Auth & Progress ----------

def home(request):
    return index(request)

def login(request):
    if request.user.is_authenticated:
        return redirect('index')

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)

        if user is not None:
            auth_login(request, user)
            progress_url = reverse('progress') + '?next=' + reverse('index')
            return redirect(progress_url)
        else:
            messages.error(request, "Ungültiger Benutzername oder Passwort")

    return render(request, "login.html")


@login_required
def progress(request):
    target = request.GET.get('next') or reverse('index')
    return render(request, "progress.html", {"redirect_to": target})


def logout_view(request):
    logout(request)
    return redirect('login')


# ---------- Access Helpers ----------

def _is_admin(user):
    return user.is_superuser or user.is_staff

def _can_view_patient(user, patient):
    if not user.is_authenticated:
        return False
    if _is_admin(user):
        return True
    if patient.usrID_id == user.id:
        return True
    if patient.visibility == Patient.Visibility.PUBLIC_ORG:
        return True
    if patient.visibility == Patient.Visibility.SHARED and patient.shared_with.filter(id=user.id).exists():
        return True
    return False


def _can_edit_patient(user, patient):
    return _is_admin(user) or (patient.usrID_id == user.id)

def _can_access_patient(user, patient):
    return _can_view_patient(user, patient)


# ---------- Main Pages ----------

@login_required
def index(request):
    users = User.objects.exclude(id=request.user.id)
    avatar = Profile.objects.filter(user=request.user).first()

    scope = request.GET.get('scope', 'all')

    base_qs = Patient.objects.visible_to(request.user) \
        .select_related('usrID') \
        .prefetch_related('shared_with')

    owner = request.GET.get('owner')
    if owner and request.user.is_staff:
        base_qs = base_qs.filter(usrID_id=owner)

    if scope == 'mine':
        patients = base_qs.filter(usrID=request.user)
    elif scope == 'shared':
        patients = base_qs.filter(shared_with=request.user) \
                          .exclude(usrID=request.user) \
                          .exclude(visibility=Patient.Visibility.PUBLIC_ORG) \
                          .distinct()
    else:
        patients = base_qs

    counts = {
        'all': base_qs.count(),
        'mine': base_qs.filter(usrID=request.user).count(),
        'shared': base_qs.filter(shared_with=request.user)
                         .exclude(usrID=request.user)
                         .exclude(visibility=Patient.Visibility.PUBLIC_ORG)
                         .distinct()
                         .count(),
    }

    return render(request, 'index.html', {
        'users': users,
        'patients': patients,
        'avatar': avatar,
        'scope': scope,
        'counts': counts,
    })


@login_required
def patient_manage(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    users = User.objects.exclude(id=request.user.id)

    if request.method == "POST":
        form_type = request.POST.get("form")

        if not _can_edit_patient(request.user, patient):
            messages.error(request, "Nur Eigentümer oder Manager/Admin dürfen diesen Patienten bearbeiten oder teilen.")
            return redirect('patient_manage', patient_id=patient.id)

        # ---- Details speichern ----
        if form_type == "details":
            patient.ptnName = (request.POST.get("ptnName") or patient.ptnName).strip()
            patient.ptnLastname = (request.POST.get("ptnLastname") or patient.ptnLastname).strip()
            patient.ptnDOB = request.POST.get("ptnDOB") or patient.ptnDOB
            patient.save()
            messages.success(request, "Patientendaten gespeichert.")
            return redirect('patient_manage', patient_id=patient.id)

        # ---- Sichtbarkeit ändern (PRIVATE / PUBLIC_ORG via normal submit) ----
        elif form_type == "visibility":
            vis = request.POST.get("visibility")
            allowed = {
                Patient.Visibility.PRIVATE,
                Patient.Visibility.SHARED,       # will be handled by modal, but keep safe
                Patient.Visibility.PUBLIC_ORG,
            }
            if vis not in allowed:
                messages.error(request, "Ungültige Sichtbarkeit.")
                return redirect('patient_manage', patient_id=patient.id)

            # If user tries to submit SHARED via this form, redirect them to use modal
            if vis == Patient.Visibility.SHARED:
                messages.info(request, "Bitte wählen Sie Benutzer im Dialog aus.")
                return redirect('patient_manage', patient_id=patient.id)

            # PRIVATE or PUBLIC_ORG:
            patient.visibility = vis
            patient.save(update_fields=['visibility'])

            # If switching to PRIVATE, clear shares
            if vis == Patient.Visibility.PRIVATE:
                patient.shared_with.clear()

            messages.success(request, "Sichtbarkeit aktualisiert.")
            return redirect('patient_manage', patient_id=patient.id)

        # ---- Set shared via modal (visibility + shares in einem Schritt) ----
        elif form_type == "set_shared":
            ids = request.POST.getlist("share_with")
            share_set = User.objects.filter(id__in=ids).exclude(id=patient.usrID_id)

            if not share_set.exists():
                messages.error(request, "Bitte mindestens einen Benutzer auswählen, um zu teilen.")
                return redirect('patient_manage', patient_id=patient.id)

            patient.shared_with.set(share_set)
            patient.visibility = Patient.Visibility.SHARED
            patient.save(update_fields=['visibility'])
            messages.success(request, "Patient wurde geteilt.")
            return redirect('patient_manage', patient_id=patient.id)

        # ---- Thumbnail hochladen ----
        elif form_type == "thumb":
            if 'thumbnail' in request.FILES:
                patient.thumbnail = request.FILES['thumbnail']
                patient.save()
                messages.success(request, "Thumbnail aktualisiert.")
            else:
                messages.error(request, "Keine Bilddatei ausgewählt.")
            return redirect('patient_manage', patient_id=patient.id)

        # ---- Thumbnail entfernen ----
        elif form_type == "thumb_remove":
            if patient.thumbnail:
                patient.thumbnail.delete(save=False)
                patient.thumbnail = None
                patient.save()
                messages.success(request, "Thumbnail entfernt.")
            return redirect('patient_manage', patient_id=patient.id)

    return render(request, 'patient_manage.html', {
        'patient': patient,
        'users': users,
        'can_edit': _can_edit_patient(request.user, patient),
    })

# ---------- Misc Pages ----------

@login_required
def load_new_fall(request):
    return render(request, 'newFall.html')

@login_required
def patient_list(request):
    return redirect('index')


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
            usrID=request.user,
            visibility=Patient.Visibility.PUBLIC_ORG,  # ensure default "Öffentlich"
        )
        return redirect('index')

    return redirect('index')


# ---------- Patient Detail & Comments ----------

@login_required
def patient_image(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)

    if not _can_view_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    models3d = Model3D.objects.filter(ptnID=patient).order_by('-id')
    images = Image.objects.filter(ptnID=patient)
    videos = patient.videos.all().order_by('-uploaded_at')
    comments = Comment.objects.filter(patient=patient).select_related('author', 'author__profile')

    return render(request, 'patientImage.html', {
        'patient': patient,
        'images': images,
        'videos': videos,
        'comments': comments,
        'can_comment': _can_view_patient(request.user, patient),
        'models3d': models3d
    })


@require_POST
@login_required
def add_comment(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_view_patient(request.user, patient):
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


# ---------- Images ----------

@login_required
def upload_images(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    if request.method == 'POST' and request.FILES.getlist('images'):
        for file in request.FILES.getlist('images'):
            Image.objects.create(
                ptnID=patient,
                usrID=request.user,
                image=file,
                imgDesc=''
            )
    return redirect('patientImage', patient_id=patient.id)


@login_required
def delete_images(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    if request.method == 'POST':
        image_ids = request.POST.getlist('selected_images')
        Image.objects.filter(id__in=image_ids, ptnID=patient).delete()
    return redirect('patientImage', patient_id=patient_id)


@login_required
def delete_single_image(request, image_id):
    image = get_object_or_404(Image, id=image_id)
    patient = image.ptnID
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    image.delete()
    return redirect('patientImage', patient_id=patient.id)


# ---------- Patient Delete ----------

@login_required
def delete_patient(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    patient.delete()
    return redirect('index')


# ---------- Messaging / Settings ----------

@login_required
def get_unread_message_count(request):
    count = Message.objects.filter(receiver=request.user, is_read=False).count()
    return JsonResponse({'unread_count': count})


@login_required
def user_settings(request):
    avatar_nums = range(1, 15)
    user = request.user
    profile, created = Profile.objects.get_or_create(user=user)

    if request.method == "POST":
        profile = user.profile

        # Basic fields
        user.username   = request.POST.get("username", user.username)
        user.first_name = request.POST.get("first_name", user.first_name)
        user.last_name  = request.POST.get("last_name", user.last_name)
        user.email      = request.POST.get("email", user.email)

        # Avatar: uploaded file takes precedence over URL choice
        uploaded = request.FILES.get("avatar_file")
        if uploaded:
            # Validate
            ctype_ok = (uploaded.content_type or "").lower().startswith("image/")
            size_ok  = uploaded.size <= 5 * 1024 * 1024  # 5 MB
            if not ctype_ok:
                messages.error(request, "Ungültiger Bildtyp. Bitte PNG/JPG hochladen.")
                return redirect("user_settings")
            if not size_ok:
                messages.error(request, "Das Bild ist zu groß (max. 5 MB).")
                return redirect("user_settings")

            # Save to MEDIA_ROOT/avatars/
            name, ext = os.path.splitext(uploaded.name or "")
            ext = ext.lower() if ext else ".jpg"
            fname = f"avatars/u{user.id}_{uuid.uuid4().hex}{ext}"
            saved_path = default_storage.save(fname, uploaded)  # relative path inside MEDIA_ROOT

            # Optionally delete previous uploaded file if it was local
            old_url = profile.avatar_url or ""
            if old_url.startswith(settings.MEDIA_URL):
                try:
                    old_rel = old_url.replace(settings.MEDIA_URL, "", 1)
                    if default_storage.exists(old_rel):
                        default_storage.delete(old_rel)
                except Exception:
                    pass

            # Store URL to the uploaded file
            profile.avatar_url = f"{settings.MEDIA_URL}{saved_path}"

        else:
            # Use selected preset URL (if any)
            profile.avatar_url = request.POST.get("avatar_url") or profile.avatar_url

        # Save profile first (so avatar persists even if password step alters session)
        profile.save()

        # Password (optional)
        password = request.POST.get("password")
        if password:
            user.set_password(password)
            update_session_auth_hash(request, user)  # keep user logged in

        user.save()
        messages.success(request, "Profil erfolgreich aktualisiert!")
        return redirect("user_settings")

    return render(request, "user_settings.html", {"avatar_nums": avatar_nums})


# ---------- Videos ----------

@login_required
def upload_videos(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    if request.method == 'POST' and request.FILES.getlist('videos'):
        for f in request.FILES.getlist('videos'):
            Video.objects.create(ptnID=patient, usrID=request.user, file=f, vidDesc='')
    return redirect('patientImage', patient_id=patient.id)


@login_required
def delete_videos(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    if request.method == 'POST':
        ids = request.POST.getlist('selected_videos')
        Video.objects.filter(id__in=ids, ptnID=patient).delete()
    return redirect('patientImage', patient_id=patient.id)


@login_required
def delete_single_video(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    patient = video.ptnID
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    video.delete()
    return redirect('patientImage', patient_id=patient.id)


# ---------- 3D Models ----------

@login_required
@require_POST
def upload_models(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    files = request.FILES.getlist('models')
    for f in files:
        name = (f.name or '').lower()
        ctype = (f.content_type or '').lower()
        if not (name.endswith('.stl') or 'model/stl' in ctype or 'application/sla' in ctype):
            continue
        Model3D.objects.create(ptnID=patient, usrID=request.user, file=f)

    return redirect('patientImage', patient_id=patient.id)


@login_required
@require_POST
def delete_models(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    ids = request.POST.getlist('selected_models')
    Model3D.objects.filter(ptnID=patient, id__in=ids).delete()
    return redirect('patientImage', patient_id=patient_id)


@login_required
def delete_single_model(request, model_id):
    m = get_object_or_404(Model3D, id=model_id)
    patient = m.ptnID
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    pid = patient.id
    m.delete()
    return redirect('patientImage', patient_id=pid)


# ---------- Feedback ----------

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

    for f in request.FILES.getlist('attachments')[:5]:
        if f.content_type.startswith('image/') and f.size <= 10 * 1024 * 1024:
            email.attach(f.name, f.read(), f.content_type)

    email.send(fail_silently=False)
    return JsonResponse({'ok': True})
