# SmileHealth/signals.py

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
from django.contrib.auth.signals import user_logged_in

from .models import Profile, Patient, Image, Comment, Model3D, Message, ActivityLog
# Import Video if you added it (safe if missing)
try:
    from .models import Video
except Exception:  # pragma: no cover
    Video = None

# ── Role groups we keep in sync with Profile.role ──────────────────────────────
ROLE_GROUPS = ["ADMIN", "MANAGER", "DOCTOR", "ASSISTANT", "VIEWER"]


def _ensure_role_groups_exist():
    """Create missing Django Groups for our roles (idempotent)."""
    for name in ROLE_GROUPS:
        Group.objects.get_or_create(name=name)


def _sync_user_groups_to_role(user: User, role: str):
    """
    Make sure the user is a member of exactly the one Group named like role,
    and not a member of the other role groups.
    """
    _ensure_role_groups_exist()
    # remove from all role groups
    user.groups.remove(*user.groups.filter(name__in=ROLE_GROUPS))
    # add to matching role group
    if role in ROLE_GROUPS:
        grp, _ = Group.objects.get_or_create(name=role)
        user.groups.add(grp)


def _sync_user_staff_flag(user: User, role: str):
    """
    ADMIN/MANAGER => is_staff True; others => False unless user.is_superuser.
    Use update() to avoid recursive save signals.
    """
    should_be_staff = (role in ("ADMIN", "MANAGER")) or user.is_superuser
    if user.is_staff != should_be_staff:
        User.objects.filter(pk=user.pk).update(is_staff=should_be_staff)


def _log_activity(action, actor=None, target=None, details=""):
    target_type = ""
    target_id = None
    target_label = ""
    if target is not None:
        target_type = target.__class__.__name__
        target_id = getattr(target, "pk", None)
        try:
            target_label = str(target)
        except Exception:
            target_label = ""

    ActivityLog.objects.create(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        target_label=target_label,
        details=details,
    )


# ── Profile auto-create / auto-save + role/group sync ─────────────────────────
@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    """
    Create a Profile when a User is created; on update, keep it saved.
    Also sync is_staff and Group membership from Profile.role.
    """
    if created:
        profile = Profile.objects.create(user=instance)  # default role = VIEWER
    else:
        profile, _ = Profile.objects.get_or_create(user=instance)
        # Keep profile saved (your previous logic)
        try:
            instance.profile.save()
        except Exception:
            pass

    # If Profile has a role field (it should), sync staff flag + groups
    role = getattr(profile, "role", "VIEWER")
    _sync_user_staff_flag(instance, role)
    _sync_user_groups_to_role(instance, role)


@receiver(post_save, sender=Profile)
def sync_user_on_profile_change(sender, instance: Profile, **kwargs):
    """
    When Profile changes (e.g., role updated), reflect it on the related User:
    - Update is_staff according to role (ADMIN/MANAGER ⇒ staff)
    - Sync Django Group membership to match the role
    """
    user = instance.user
    role = getattr(instance, "role", "VIEWER")
    _sync_user_staff_flag(user, role)
    _sync_user_groups_to_role(user, role)


@receiver(user_logged_in)
def log_user_login(sender, request, user, **kwargs):
    _log_activity(ActivityLog.Action.LOGIN, actor=user, target=user)


# ── Patient thumbnail housekeeping ─────────────────────────────────────────────
@receiver(post_delete, sender=Patient)
def delete_thumb_on_patient_delete(sender, instance, **kwargs):
    """
    When a Patient is deleted, also remove the thumbnail file from storage.
    """
    if instance.thumbnail:
        instance.thumbnail.delete(save=False)


@receiver(post_save, sender=Patient)
def log_patient_created(sender, instance, created, **kwargs):
    if created:
        _log_activity(ActivityLog.Action.PATIENT_CREATED, actor=instance.usrID, target=instance)


@receiver(post_delete, sender=Patient)
def log_patient_deleted(sender, instance, **kwargs):
    _log_activity(ActivityLog.Action.PATIENT_DELETED, actor=instance.usrID, target=instance)


@receiver(pre_save, sender=Patient)
def delete_old_thumb_on_change(sender, instance, **kwargs):
    """
    If the Patient's thumbnail is being replaced, delete the old file to avoid
    orphaned files in MEDIA_ROOT.
    """
    if not instance.pk:
        return  # new instance; nothing to compare
    try:
        old = Patient.objects.get(pk=instance.pk)
    except Patient.DoesNotExist:
        return
    # If the file object changed, remove the old one
    if old.thumbnail and old.thumbnail != instance.thumbnail:
        old.thumbnail.delete(save=False)


# ── Image / Video file cleanup ─────────────────────────────────────────────────
@receiver(post_delete, sender=Image)
def delete_image_file_on_row_delete(sender, instance, **kwargs):
    """
    When an Image row is deleted, remove its file from storage.
    """
    if instance.image:
        instance.image.delete(save=False)


@receiver(post_save, sender=Image)
def log_image_uploaded(sender, instance, created, **kwargs):
    if created:
        _log_activity(ActivityLog.Action.IMAGE_UPLOADED, actor=instance.usrID, target=instance)


@receiver(post_delete, sender=Image)
def log_image_deleted(sender, instance, **kwargs):
    _log_activity(ActivityLog.Action.IMAGE_DELETED, actor=instance.usrID, target=instance)


@receiver(post_save, sender=Comment)
def log_comment_added(sender, instance, created, **kwargs):
    if created:
        _log_activity(ActivityLog.Action.COMMENT_ADDED, actor=instance.author, target=instance)


@receiver(post_save, sender=Message)
def log_message_sent(sender, instance, created, **kwargs):
    if created:
        _log_activity(ActivityLog.Action.MESSAGE_SENT, actor=instance.sender, target=instance)


@receiver(post_save, sender=Model3D)
def log_model3d_uploaded(sender, instance, created, **kwargs):
    if created:
        _log_activity(ActivityLog.Action.MODEL3D_UPLOADED, actor=instance.usrID, target=instance)


@receiver(post_delete, sender=Model3D)
def log_model3d_deleted(sender, instance, **kwargs):
    _log_activity(ActivityLog.Action.MODEL3D_DELETED, actor=instance.usrID, target=instance)


if Video:
    @receiver(post_delete, sender=Video)
    def delete_video_file_on_row_delete(sender, instance, **kwargs):
        """
        When a Video row is deleted, remove its file from storage.
        """
        if instance.file:
            instance.file.delete(save=False)


    @receiver(post_save, sender=Video)
    def log_video_uploaded(sender, instance, created, **kwargs):
        if created:
            _log_activity(ActivityLog.Action.VIDEO_UPLOADED, actor=instance.usrID, target=instance)


    @receiver(post_delete, sender=Video)
    def log_video_deleted(sender, instance, **kwargs):
        _log_activity(ActivityLog.Action.VIDEO_DELETED, actor=instance.usrID, target=instance)
