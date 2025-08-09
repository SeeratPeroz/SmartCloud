from django.apps import AppConfig


class SmilehealthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'SmileHealth'

    def ready(self):
        import SmileHealth.signals  # Impor