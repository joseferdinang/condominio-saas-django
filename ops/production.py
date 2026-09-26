"""Safe pilot operations. Python stdlib only; invoke from the host, not the app."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_media_archive(path):
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = PurePosixPath(member.name)
            if name.is_absolute() or ".." in name.parts or "\\" in member.name:
                raise ValueError("Ruta insegura en el respaldo de documentos.")
            if not (member.isfile() or member.isdir()):
                raise ValueError("El respaldo solo puede contener archivos y directorios.")


def validate_backup(folder):
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1:
        raise ValueError("Formato de respaldo desconocido.")
    expected = {"postgres.dump", "media.tar.gz", "verification.json"}
    if set(manifest.get("sha256", {})) != expected:
        raise ValueError("Respaldo incompleto.")
    for filename, checksum in manifest["sha256"].items():
        if digest(folder / filename) != checksum:
            raise ValueError(f"No coincide SHA-256: {filename}.")
    validate_media_archive(folder / "media.tar.gz")
    return manifest


@contextmanager
def operation_lock(project):
    folder = ROOT / ".ops-locks"
    folder.mkdir(mode=0o700, exist_ok=True)
    with (folder / f"{project}.lock").open("a+b") as stream:
        stream.seek(0)
        stream.write(b"0")
        stream.flush()
        stream.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class Production:
    def __init__(self, args):
        self.project = args.project
        self.environment = os.environ.copy()
        self.environment["ENV_FILE"] = str(Path(args.env_file).resolve())
        self.environment["SECRETS_DIR"] = str(Path(args.secrets_dir).resolve())
        self.command = [
            "docker", "compose", "--project-name", self.project,
            "--env-file", self.environment["ENV_FILE"],
            "-f", str(ROOT / "compose.production.yaml"),
        ]

    def dc(self, *args, **kwargs):
        return subprocess.run(
            [*self.command, *args], cwd=ROOT, env=self.environment,
            check=True, **kwargs,
        )

    def text(self, *args):
        return self.dc(*args, stdout=subprocess.PIPE, text=True).stdout.strip()

    def db(self, command, **kwargs):
        return self.dc("exec", "-T", "db", "sh", "-ec", command, **kwargs)

    def running_web(self):
        return bool(self.text("ps", "--status", "running", "--quiet", "web"))

    def snapshot(self):
        return json.loads(self.text(
            "run", "--rm", "--no-deps", "-T", "maintenance",
            "python", "ops/snapshot.py",
        ))

    def backup(self, output):
        # Stop the only web writer; the same host lock excludes cron/migrations.
        if not self.text("ps", "--status", "running", "--quiet", "db"):
            raise ValueError("PostgreSQL debe estar en ejecución.")
        folder = Path(output).resolve() / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        folder.mkdir(parents=True, mode=0o700)
        was_running = self.running_web()
        if was_running:
            self.dc("stop", "web")
        try:
            with (folder / "postgres.dump").open("xb") as stream:
                self.db('pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc --no-owner --no-privileges', stdout=stream)
            with (folder / "media.tar.gz").open("xb") as stream:
                self.dc("run", "--rm", "--no-deps", "-T", "maintenance", "tar", "-czf", "-", "-C", "/app/media", ".", stdout=stream)
            (folder / "verification.json").write_text(
                json.dumps(self.snapshot(), sort_keys=True), encoding="utf-8",
            )
            validate_media_archive(folder / "media.tar.gz")
            manifest = {
                "format": 1,
                "project": self.project,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "postgres_major": 17,
                "image_id": self.text("images", "--quiet", "web"),
                "sha256": {name: digest(folder / name) for name in (
                    "postgres.dump", "media.tar.gz", "verification.json",
                )},
            }
            (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            for path in folder.iterdir():
                path.chmod(0o600)
            print(f"Respaldo completo y verificado: {folder}", flush=True)
        finally:
            if was_running:
                self.dc("start", "web")
        return folder

    def restore(self, backup):
        folder = Path(backup).resolve()
        manifest = validate_backup(folder)
        if manifest["project"] == self.project:
            raise ValueError("Restaura en un proyecto nuevo, distinto del origen.")
        if self.running_web():
            raise ValueError("El destino no debe tener web en ejecución.")
        self.dc("up", "--detach", "--wait", "db")
        result = self.db(
            'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc '
            '"SELECT count(*) FROM pg_tables WHERE schemaname NOT IN (\'pg_catalog\', \'information_schema\');"',
            stdout=subprocess.PIPE, text=True,
        ).stdout.strip()
        if result != "0":
            raise ValueError("La base de destino no está vacía. No se modificó.")
        entries = self.text(
            "run", "--rm", "--no-deps", "-T", "maintenance", "python", "-c",
            "from pathlib import Path; print(len(list(Path('/app/media').iterdir())))",
        )
        if entries != "0":
            raise ValueError("El volumen de documentos no está vacío. No se modificó.")
        with (folder / "postgres.dump").open("rb") as stream:
            self.db('pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --single-transaction --exit-on-error --no-owner --no-privileges', stdin=stream)
        with (folder / "media.tar.gz").open("rb") as stream:
            self.dc("run", "--rm", "--no-deps", "-T", "maintenance", "tar", "-xzf", "-", "-C", "/app/media", "--no-same-owner", stdin=stream)
        expected = json.loads((folder / "verification.json").read_text(encoding="utf-8"))
        if self.snapshot() != expected:
            raise ValueError("La verificación no coincide. Web permanece detenido; conserva el destino para investigar.")
        print("Restauración verificada: filas y huellas de todas las tablas y documentos coinciden. Web permanece detenido.")


def init_secrets(folder):
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name != "nt":
        folder.chmod(0o700)
    names = ["django_secret_key", "postgres_password"]
    if any((folder / name).exists() for name in names):
        raise ValueError("Ya existen secretos. No se sobrescriben ni rotan automáticamente.")
    for name in names:
        with (folder / name).open("x", encoding="utf-8") as stream:
            stream.write(secrets.token_urlsafe(64))
        # Parent is 0700; a read-only Docker secret must be readable by app UID 10001.
        (folder / name).chmod(0o600 if os.name == "nt" else 0o444)
    print(f"Secretos generados en {folder}; valores no mostrados.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=str(ROOT / ".env.production"))
    parser.add_argument("--secrets-dir", default=str(ROOT / ".secrets"))
    parser.add_argument("--project", default="condominio-prod")
    commands = parser.add_subparsers(dest="action", required=True)
    commands.add_parser("init-secrets")
    commands.add_parser("dc").add_argument("arguments", nargs=argparse.REMAINDER)
    commands.add_parser("backup").add_argument("--output", default=str(ROOT / "backups"))
    commands.add_parser("restore").add_argument("backup")
    quotas = commands.add_parser("cuotas")
    quotas.add_argument("--edificio", type=int, required=True)
    quotas.add_argument("--usuario", required=True)
    quotas.add_argument("--dia-vencimiento", type=int, default=10)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,62}", args.project):
        parser.error("Nombre de proyecto no válido.")
    os.umask(0o077)
    try:
        if args.action == "init-secrets":
            init_secrets(args.secrets_dir)
            return
        runtime = Production(args)
        with operation_lock(args.project):
            if args.action == "dc":
                runtime.dc(*args.arguments)
            elif args.action == "backup":
                runtime.backup(args.output)
            elif args.action == "restore":
                runtime.restore(args.backup)
            elif args.action == "cuotas":
                runtime.dc("exec", "-T", "web", "python", "manage.py", "generar_cuotas", "--actual",
                           "--edificio", str(args.edificio), "--usuario", args.usuario,
                           "--dia-vencimiento", str(args.dia_vencimiento))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Operación incompleta: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
