# SmileHealth/context_processors.py
from .models import Profile

def user_avatar(request):
    """
    Make `avatar` available in ALL templates.
    Ensures a Profile exists for the logged-in user.
    """
    if not request.user.is_authenticated:
        return {}
    profile, _ = Profile.objects.get_or_create(user=request.user)
    return {"avatar": profile}
