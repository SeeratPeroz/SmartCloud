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
from django.utils.timesince import timesince
import os, uuid, time, threading
from django.core.files.storage import default_storage


from .models import (
    Patient, Image, Message, Profile, Video, Comment, Model3D, ActivityLog, CaseGroup
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

def _is_admin_role(user):
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    try:
        return user.profile.role == Profile.Role.ADMIN
    except Exception:
        return False


def _can_view_group(user, group):
    if not user.is_authenticated:
        return False
    if _is_admin(user):
        return True
    if group.created_by_id == user.id:
        return True
    if group.visibility == CaseGroup.Visibility.SHARED and group.shared_with.filter(id=user.id).exists():
        return True
    return False


def _can_manage_group(user, group):
    return _is_admin(user) or group.created_by_id == user.id


def _can_create_in_group(user, group):
    if _is_admin(user) or group.created_by_id == user.id:
        return True
    if group.visibility == CaseGroup.Visibility.SHARED and group.shared_with.filter(id=user.id).exists():
        return True
    return False


def _default_avatar_for_gender(gender):
    if gender == Profile.Gender.FEMALE:
        return "https://randomuser.me/api/portraits/women/1.jpg"
    if gender == Profile.Gender.MALE:
        return "https://randomuser.me/api/portraits/men/1.jpg"
    return "https://i.pravatar.cc/150?img=1"

def _can_view_patient(user, patient):
    if not user.is_authenticated:
        return False
    if _is_admin(user):
        return True
    if patient.group_id:
        return _can_view_group(user, patient.group)
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


def _safe_delete_file(path, attempts=20, delay=0.5):
    """Delete a file on disk with retries; tries rename first to break Windows locks."""
    if not path:
        return
    base_dir = os.path.dirname(path) or '.'
    for i in range(max(1, attempts)):
        try:
            if os.path.exists(path):
                # try rename to temp name to release lock
                tmp_name = os.path.join(base_dir, f".__del_{uuid.uuid4().hex}")
                try:
                    os.replace(path, tmp_name)
                    path = tmp_name
                except PermissionError:
                    pass
                if os.path.exists(path):
                    os.remove(path)
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)


# ---------- Main Pages ----------

@login_required
def index(request):
    users = User.objects.exclude(id=request.user.id)
    avatar = Profile.objects.filter(user=request.user).first()

    unread_count = Message.objects.filter(receiver=request.user, is_read=False).count()
    last_notified = request.session.get("unread_notice_count", 0)
    if unread_count > 0 and unread_count != last_notified:
        messages.info(request, f"Sie haben {unread_count} ungelesene Nachricht(en).")
        request.session["unread_notice_count"] = unread_count

    scope = request.GET.get('scope', 'all')

    base_qs = Patient.objects.visible_to(request.user) \
        .select_related('usrID') \
        .prefetch_related('shared_with')

    owner = request.GET.get('owner')
    if owner and request.user.is_staff:
        base_qs = base_qs.filter(usrID_id=owner)

    base_non_group = base_qs.filter(group__isnull=True)

    if scope == 'mine':
        patients = base_non_group.filter(usrID=request.user)
    elif scope == 'shared':
        patients = base_non_group.filter(shared_with=request.user) \
                                 .exclude(usrID=request.user) \
                                 .exclude(visibility=Patient.Visibility.PUBLIC_ORG) \
                                 .distinct()
    else:
        patients = base_non_group

    counts = {
        'all': base_non_group.count(),
        'mine': base_non_group.filter(usrID=request.user).count(),
        'shared': base_non_group.filter(shared_with=request.user)
                         .exclude(usrID=request.user)
                         .exclude(visibility=Patient.Visibility.PUBLIC_ORG)
                         .distinct()
                         .count(),
    }

    if _is_admin(request.user):
        groups = CaseGroup.objects.all()
    else:
        groups = CaseGroup.objects.filter(
            Q(created_by=request.user)
            | (Q(visibility=CaseGroup.Visibility.SHARED) & Q(shared_with=request.user))
        ).distinct()

    return render(request, 'index.html', {
        'users': users,
        'patients': patients,
        'groups': groups,
        'avatar': avatar,
        'scope': scope,
        'counts': counts,
        'unread_count': unread_count,
    })


@login_required
def group_create(request):
    if request.method != "POST":
        return redirect('index')

    name = (request.POST.get("name") or "").strip()
    description = (request.POST.get("description") or "").strip()
    visibility = request.POST.get("visibility") or CaseGroup.Visibility.PRIVATE

    if not name:
        messages.error(request, "Gruppenname ist erforderlich.")
        return redirect('index')

    if visibility not in {CaseGroup.Visibility.PRIVATE, CaseGroup.Visibility.SHARED}:
        visibility = CaseGroup.Visibility.PRIVATE

    group = CaseGroup.objects.create(
        name=name,
        description=description,
        created_by=request.user,
        visibility=visibility,
    )

    if visibility == CaseGroup.Visibility.SHARED:
        ids = request.POST.getlist("share_with")
        share_set = User.objects.filter(id__in=ids).exclude(id=request.user.id)
        group.shared_with.set(share_set)

    ActivityLog.objects.create(
        actor=request.user,
        action=ActivityLog.Action.GROUP_CREATED,
        target_type="CaseGroup",
        target_id=group.id,
        target_label=group.name,
        details=f"visibility={group.visibility}",
    )

    messages.success(request, "Gruppe erstellt.")
    return redirect('group_detail', group_id=group.id)


@login_required
def group_detail(request, group_id):
    group = get_object_or_404(CaseGroup, id=group_id)
    if not _can_view_group(request.user, group):
        return HttpResponseForbidden("Kein Zugriff")

    if request.method == "POST":
        form_type = request.POST.get("form")

        if form_type in {"update_group", "share_group"} and not _can_manage_group(request.user, group):
            messages.error(request, "Nur Eigentümer oder Admin dürfen diese Gruppe verwalten.")
            return redirect('group_detail', group_id=group.id)

        if form_type == "update_group":
            name = (request.POST.get("name") or group.name).strip()
            description = (request.POST.get("description") or "").strip()
            visibility = request.POST.get("visibility") or group.visibility

            if visibility not in {CaseGroup.Visibility.PRIVATE, CaseGroup.Visibility.SHARED}:
                visibility = group.visibility

            group.name = name or group.name
            group.description = description
            group.visibility = visibility
            group.save()

            if visibility == CaseGroup.Visibility.PRIVATE:
                group.shared_with.clear()

            ActivityLog.objects.create(
                actor=request.user,
                action=ActivityLog.Action.GROUP_UPDATED,
                target_type="CaseGroup",
                target_id=group.id,
                target_label=group.name,
                details=f"visibility={group.visibility}",
            )

            messages.success(request, "Gruppendaten gespeichert.")
            return redirect('group_detail', group_id=group.id)

        if form_type == "share_group":
            ids = request.POST.getlist("share_with")
            share_set = User.objects.filter(id__in=ids).exclude(id=group.created_by_id)
            group.shared_with.set(share_set)
            group.visibility = CaseGroup.Visibility.SHARED
            group.save(update_fields=["visibility"])
            ActivityLog.objects.create(
                actor=request.user,
                action=ActivityLog.Action.GROUP_SHARED,
                target_type="CaseGroup",
                target_id=group.id,
                target_label=group.name,
                details=f"shared_with={share_set.count()}",
            )
            messages.success(request, "Gruppe wurde geteilt.")
            return redirect('group_detail', group_id=group.id)

    cases = group.patients.select_related("usrID").order_by("-id")
    group_activities = ActivityLog.objects.select_related("actor") \
        .filter(target_type="CaseGroup", target_id=group.id) \
        .order_by("-created_at")[:20]

    return render(request, "group_detail.html", {
        "group": group,
        "cases": cases,
        "can_manage": _can_manage_group(request.user, group),
        "users": User.objects.exclude(id=request.user.id),
        "groups": [group],
        "group_activities": group_activities,
    })


@login_required
def admin_dashboard(request):
    if not _is_admin_role(request.user):
        return HttpResponseForbidden("Kein Zugriff")

    tab = (request.GET.get("tab") or "activities").strip()
    role_filter = (request.GET.get("role") or "").strip()
    user_id = (request.GET.get("user_id") or "").strip()
    activity_q = (request.GET.get("q") or "").strip()

    users_qs = User.objects.select_related("profile").order_by("username")
    if role_filter:
        users_qs = users_qs.filter(profile__role=role_filter)

    selected_user = None
    selected_user_activities = []
    if user_id.isdigit():
        selected_user = User.objects.select_related("profile").filter(id=int(user_id)).first()
        if selected_user:
            selected_user_activities = ActivityLog.objects.select_related("actor") \
                .filter(actor=selected_user) \
                .order_by("-created_at")[:10]

    activities_qs = ActivityLog.objects.select_related("actor").order_by("-created_at")
    if activity_q:
        activities_qs = activities_qs.filter(
            Q(actor__username__icontains=activity_q)
            | Q(action__icontains=activity_q)
            | Q(target_type__icontains=activity_q)
            | Q(target_label__icontains=activity_q)
            | Q(details__icontains=activity_q)
        )
    activities = activities_qs[:20]

    if request.method == "POST":
        form_type = request.POST.get("form")
        if form_type == "create_user":
            username = (request.POST.get("username") or "").strip()
            email = (request.POST.get("email") or "").strip()
            password = (request.POST.get("password") or "").strip()
            role = request.POST.get("role") or Profile.Role.VIEWER
            gender = request.POST.get("gender") or Profile.Gender.UNSPECIFIED

            valid_roles = {r for r, _ in Profile.Role.choices}
            valid_genders = {g for g, _ in Profile.Gender.choices}

            if not username or not password:
                messages.error(request, "Username and password are required.")
            elif User.objects.filter(username=username).exists():
                messages.error(request, "Username already exists.")
            else:
                user = User.objects.create_user(username=username, email=email, password=password)
                profile = user.profile
                profile.role = role if role in valid_roles else Profile.Role.VIEWER
                profile.gender = gender if gender in valid_genders else Profile.Gender.UNSPECIFIED
                profile.avatar_url = _default_avatar_for_gender(profile.gender)
                profile.save()

                ActivityLog.objects.create(
                    actor=request.user,
                    action=ActivityLog.Action.USER_CREATED,
                    target_type="User",
                    target_id=user.id,
                    target_label=user.username,
                )
                messages.success(request, "User created successfully.")

                redirect_url = f"{reverse('admin_dashboard')}?tab=users"
                return redirect(redirect_url)

        if form_type == "toggle_user":
            target_id = request.POST.get("user_id") or ""
            desired_state = request.POST.get("active")
            if target_id.isdigit():
                target = User.objects.filter(id=int(target_id)).first()
            else:
                target = None

            if not target:
                messages.error(request, "Benutzer nicht gefunden.")
            elif target.id == request.user.id:
                messages.error(request, "Sie können Ihr eigenes Konto nicht deaktivieren.")
            else:
                should_activate = desired_state == "1"
                target.is_active = should_activate
                target.save(update_fields=["is_active"])
                if should_activate:
                    messages.success(request, "Benutzer wurde aktiviert.")
                else:
                    messages.success(request, "Benutzer wurde deaktiviert.")

            redirect_url = f"{reverse('admin_dashboard')}?tab=users"
            if role_filter:
                redirect_url += f"&role={role_filter}"
            if user_id:
                redirect_url += f"&user_id={user_id}"
            return redirect(redirect_url)

        if form_type == "edit_user":
            target_id = request.POST.get("user_id") or ""
            if target_id.isdigit():
                target = User.objects.select_related("profile").filter(id=int(target_id)).first()
            else:
                target = None

            if not target:
                messages.error(request, "Benutzer nicht gefunden.")
            else:
                target.username = (request.POST.get("username") or "").strip() or target.username
                target.email = (request.POST.get("email") or "").strip() or target.email
                target.first_name = (request.POST.get("first_name") or "").strip() or target.first_name
                target.last_name = (request.POST.get("last_name") or "").strip() or target.last_name

                # Password (optional - only if provided)
                password = (request.POST.get("password") or "").strip()
                if password:
                    target.set_password(password)

                target.save()

                # Update profile
                profile = target.profile
                gender = request.POST.get("gender", "").strip()
                description = request.POST.get("description", "").strip()
                role = request.POST.get("role", "").strip()

                valid_genders = {g for g, _ in Profile.Gender.choices}
                valid_roles = {r for r, _ in Profile.Role.choices}

                if gender in valid_genders:
                    profile.gender = gender
                if role in valid_roles:
                    profile.role = role
                if description:
                    profile.description = description
                profile.save()

                messages.success(request, f"Benutzer '{target.username}' erfolgreich aktualisiert.")

            redirect_url = f"{reverse('admin_dashboard')}?tab=users"
            if user_id:
                redirect_url += f"&user_id={user_id}"
            if role_filter:
                redirect_url += f"&role={role_filter}"
            return redirect(redirect_url)

    return render(request, "admin_dashboard.html", {
        "tab": tab,
        "users": users_qs,
        "roles": Profile.Role.choices,
        "genders": Profile.Gender.choices,
        "role_filter": role_filter,
        "selected_user": selected_user,
        "selected_user_activities": selected_user_activities,
        "activities": activities,
        "activity_q": activity_q,
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
            if patient.group_id:
                messages.error(request, "Gruppen-Faelle verwenden die Gruppen-Sichtbarkeit.")
                return redirect('patient_manage', patient_id=patient.id)
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
            if patient.group_id:
                messages.error(request, "Gruppen-Faelle werden ueber die Gruppe geteilt.")
                return redirect('patient_manage', patient_id=patient.id)
            ids = request.POST.getlist("share_with")
            share_set = User.objects.filter(id__in=ids).exclude(id=patient.usrID_id)

            if not share_set.exists():
                messages.error(request, "Bitte mindestens einen Benutzer auswählen, um zu teilen.")
                return redirect('patient_manage', patient_id=patient.id)

            patient.shared_with.set(share_set)
            patient.visibility = Patient.Visibility.SHARED
            patient.save(update_fields=['visibility'])
            ActivityLog.objects.create(
                actor=request.user,
                action=ActivityLog.Action.PATIENT_SHARED,
                target_type="Patient",
                target_id=patient.id,
                target_label=str(patient),
            )
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
    if _is_admin(request.user):
        groups = CaseGroup.objects.all()
    else:
        groups = CaseGroup.objects.filter(
            Q(created_by=request.user)
            | (Q(visibility=CaseGroup.Visibility.SHARED) & Q(shared_with=request.user))
        ).distinct()
    return render(request, 'newFall.html', {"groups": groups})

@login_required
def patient_list(request):
    return redirect('index')


@login_required
def add_patient(request):
    if request.method == "POST":
        ptnName = request.POST.get('ptnName')
        ptnLastname = request.POST.get('ptnLastname')
        ptnDOB = request.POST.get('ptnDOB')
        group_id = request.POST.get('group_id')

        group = None
        if group_id and str(group_id).isdigit():
            group = CaseGroup.objects.filter(id=int(group_id)).first()
            if not group or not _can_create_in_group(request.user, group):
                messages.error(request, "Keine Berechtigung fuer diese Gruppe.")
                return redirect('index')

        patient = Patient.objects.create(
            ptnName=ptnName,
            ptnLastname=ptnLastname,
            ptnDOB=ptnDOB,
            usrID=request.user,
            visibility=Patient.Visibility.PRIVATE if group else Patient.Visibility.PUBLIC_ORG,
            group=group,
        )
        if group:
            ActivityLog.objects.create(
                actor=request.user,
                action=ActivityLog.Action.GROUP_CASE_CREATED,
                target_type="CaseGroup",
                target_id=group.id,
                target_label=group.name,
                details=f"case={patient.ptnName} {patient.ptnLastname} (#{patient.id})",
            )
        if group:
            return redirect('group_detail', group_id=group.id)
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
    comments = Comment.objects.filter(patient=patient).select_related('author', 'author__profile').order_by('created_at')

    return render(request, 'patientImage.html', {
        'patient': patient,
        'images': images,
        'videos': videos,
        'comments': comments,
        'can_comment': _can_view_patient(request.user, patient),
        'models3d': models3d
    })


@login_required
def add_comment(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_view_patient(request.user, patient):
        return JsonResponse({'ok': False, 'error': 'Kein Zugriff'}, status=403)

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Nur POST erlaubt'}, status=405)

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
        'author_id': request.user.id,
        'avatar_url': getattr(getattr(request.user, 'profile', None), 'avatar_url', '') or '',
        'created': c.created_at.strftime('%Y-%m-%d %H:%M'),
        'created_human': timesince(c.created_at) + ' ago',
    })


@login_required
def comments_feed(request, patient_id):
    patient = get_object_or_404(Patient, id=patient_id)
    if not _can_view_patient(request.user, patient):
        return JsonResponse({'ok': False, 'error': 'Kein Zugriff'}, status=403)

    try:
        after_id = int(request.GET.get('after_id', '0'))
    except ValueError:
        after_id = 0

    qs = Comment.objects.filter(patient=patient).select_related('author', 'author__profile')
    if after_id:
        qs = qs.filter(id__gt=after_id)
    qs = qs.order_by('created_at')

    comments = []
    for c in qs:
        author = c.author
        comments.append({
            'id': c.id,
            'content': c.content,
            'author': author.get_full_name() or author.username,
            'author_id': author.id,
            'avatar_url': getattr(getattr(author, 'profile', None), 'avatar_url', '') or '',
            'created': c.created_at.strftime('%Y-%m-%d %H:%M'),
            'created_human': timesince(c.created_at) + ' ago',
        })

    return JsonResponse({'ok': True, 'comments': comments})


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

    group = patient.group
    if group:
        ActivityLog.objects.create(
            actor=request.user,
            action=ActivityLog.Action.GROUP_CASE_DELETED,
            target_type="CaseGroup",
            target_id=group.id,
            target_label=group.name,
            details=f"case={patient.ptnName} {patient.ptnLastname} (#{patient.id})",
        )

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

        # Profile fields: gender and description
        gender = request.POST.get("gender", "").strip()
        description = request.POST.get("description", "").strip()
        if gender in {g for g, _ in Profile.Gender.choices}:
            profile.gender = gender
        if description:
            profile.description = description

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
        videos = list(Video.objects.filter(id__in=ids, ptnID=patient))
        warned=False
        for v in videos:
            try:
                _safe_delete_file(getattr(v.file, 'path', ''))
            except PermissionError:
                if not warned:
                    messages.warning(request, "Einige Videos werden im Hintergrund gelöscht, da sie noch verwendet werden.")
                    warned=True
                threading.Thread(target=_safe_delete_file, args=(getattr(v.file, 'path', ''), 30, 0.6), daemon=True).start()
        Video.objects.filter(id__in=ids, ptnID=patient).delete()
    return redirect('patientImage', patient_id=patient.id)


@login_required
def delete_single_video(request, video_id):
    video = get_object_or_404(Video, id=video_id)
    patient = video.ptnID
    if not _can_edit_patient(request.user, patient):
        return HttpResponseForbidden("Kein Zugriff")

    path = getattr(video.file, 'path', '')
    try:
        _safe_delete_file(path)
    except PermissionError:
        # try background cleanup, but still remove DB row to unblock UI
        threading.Thread(target=_safe_delete_file, args=(path, 30, 0.6), daemon=True).start()
        messages.warning(request, "Datei wird verwendet. Löschung wird erneut im Hintergrund versucht.")
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
