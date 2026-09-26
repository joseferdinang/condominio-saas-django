"""Read-only fingerprints: verify recovery without exporting values to logs."""
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

import django
django.setup()

from django.apps import apps
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.migrations.recorder import MigrationRecorder


def snapshot():
    tables = {}
    models = list(apps.get_models(include_auto_created=True)) + [MigrationRecorder.Migration]
    for model in models:
        checksum = hashlib.sha256()
        count = 0
        for row in model.objects.order_by(model._meta.pk.name).values().iterator():
            checksum.update(json.dumps(row, sort_keys=True, cls=DjangoJSONEncoder).encode("utf-8"))
            checksum.update(b"\n")
            count += 1
        tables[model._meta.db_table] = {"count": count, "sha256": checksum.hexdigest()}
    files = {}
    root = Path(settings.MEDIA_ROOT)
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("No se admiten enlaces simbólicos en documentos.")
        if path.is_file():
            with path.open("rb") as stream:
                files[path.relative_to(root).as_posix()] = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"tables": tables, "files": files}


if __name__ == "__main__":
    print(json.dumps(snapshot(), sort_keys=True))
