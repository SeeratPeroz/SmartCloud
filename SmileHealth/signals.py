# SmileHealth/signals.py

from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import Profile, Patient, Image
# Import Video if you added it (safe if missing)
try:
    from .models import Video
except Exception:  # pragma: no cover
    Video = None


# ── Profile auto-create / auto-save ────────────────────────────────────────────
@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance, created, **kwargs):
    """
    Create a Profile when a User is created; on update, keep it saved.
    """
    if created:
        Profile.objects.create(user=instance)
    else:
        # If profile exists, save it; if not, create it (defensive).
        Profile.objects.get_or_create(user=instance)
        instance.profile.save()


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
