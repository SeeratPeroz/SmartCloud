# SmileHealth/apps.py
from django.apps import AppConfig


class SmilehealthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'SmileHealth'

    def ready(self):
        # Ensure signal receivers are registered
        import SmileHealth.signals  # noqa
