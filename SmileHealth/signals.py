# SmileHealth/signals.py

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group

from .models import Profile, Patient, Image
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


# ── Patient thumbnail housekeeping ─────────────────────────────────────────────
@receiver(post_delete, sender=Patient)
def delete_thumb_on_patient_delete(sender, instance, **kwargs):
    """
    When a Patient is deleted, also remove the thumbnail file from storage.
    """
    if instance.thumbnail:
        instance.thumbnail.delete(save=False)


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


if Video:
    @receiver(post_delete, sender=Video)
    def delete_video_file_on_row_delete(sender, instance, **kwargs):
        """
        When a Video row is deleted, remove its file from storage.
        """
        if instance.file:
            instance.file.delete(save=False)
