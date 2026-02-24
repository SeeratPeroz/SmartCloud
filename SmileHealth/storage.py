import os
from pathlib import Path
from django.core.files.storage import FileSystemStorage
from django.conf import settings


class PrimarySecondaryStorage(FileSystemStorage):
    """
    Custom storage backend that tries to save files to the server path first,
    then falls back to the local BASE_DIR if the server path fails.
    
    Priority order:
    1. /var/db_media/CleverCloud/media/ (server)
    2. BASE_DIR/media/ (local fallback)
    """
    
    def __init__(self, location=None, base_url=None):
        self.server_root = Path('/var/db_media/CleverCloud/media')
        self.local_root = Path(settings.BASE_DIR) / 'media'
        
        # Determine initial location based on availability
        if self.server_root.exists() and os.access(str(self.server_root), os.W_OK):
            location = str(self.server_root)
        else:
            location = str(self.local_root)
        
        super().__init__(location=location, base_url=base_url)
    
    def save(self, name, content, max_length=None):
        """
        Save a file, trying server location first, then local fallback.
        Returns the relative path to the saved file.
        """
        # Try server first
        try:
            if self.server_root.exists() and os.access(str(self.server_root), os.W_OK):
                self.location = str(self.server_root)
                self.server_root.mkdir(parents=True, exist_ok=True)
                # Reset content stream before trying
                if hasattr(content, 'seek'):
                    content.seek(0)
                return super().save(name, content, max_length)
        except (OSError, IOError, PermissionError, Exception):
            pass
        
        # Fall back to local
        try:
            self.location = str(self.local_root)
            self.local_root.mkdir(parents=True, exist_ok=True)
            # Reset content stream before trying
            if hasattr(content, 'seek'):
                content.seek(0)
            return super().save(name, content, max_length)
        except Exception as e:
            raise IOError(f"Failed to save file to both server and local paths: {str(e)}")
