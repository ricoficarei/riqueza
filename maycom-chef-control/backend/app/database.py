import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


ACTIVE = ("queued", "preparing", "submitting", "running", "validating")


def now():
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        with self.connection() as c:
            c.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at);
            """)

    @contextmanager
    def connection(self):
        c = sqlite3.connect(self.path, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        except BaseException:
            c.rollback()
            raise
        finally:
            c.close()

    def put_asset(self, asset):
        with self.connection() as c:
            c.execute("INSERT OR REPLACE INTO assets VALUES (?,?)", (asset["id"], json.dumps(asset)))

    def asset(self, ident):
        with self.connection() as c:
            row = c.execute("SELECT data FROM assets WHERE id=?", (ident,)).fetchone()
            return json.loads(row[0]) if row else None

    def assets(self):
        with self.connection() as c:
            return [json.loads(r[0]) for r in c.execute("SELECT data FROM assets ORDER BY rowid DESC")]

    def remove_asset(self, ident):
        with self.connection() as c:
            c.execute("DELETE FROM assets WHERE id=?", (ident,))

    def jobs(self):
        with self.connection() as c:
            return [json.loads(r[0]) for r in c.execute("SELECT data FROM jobs ORDER BY created_at DESC")]

    def job(self, ident):
        with self.connection() as c:
            row = c.execute("SELECT data FROM jobs WHERE id=?", (ident,)).fetchone()
            return json.loads(row[0]) if row else None

    def enqueue(self, job, max_queue):
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            count = c.execute("SELECT COUNT(*) FROM jobs WHERE status IN (?,?,?,?,?)", ACTIVE).fetchone()[0]
            if count >= max_queue:
                raise ValueError("A fila está cheia. Aguarde uma tarefa terminar.")
            c.execute("INSERT INTO jobs VALUES (?,?,?,?)", (job["id"], job["status"], job["created_at"], json.dumps(job)))

    def update_job(self, ident, *, allow_terminal=False, **changes):
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT data FROM jobs WHERE id=?", (ident,)).fetchone()
            if not row:
                return None
            data = json.loads(row[0])
            if data["status"] not in ACTIVE and not allow_terminal:
                return data
            message = changes.pop("message", None)
            data.update(changes)
            data["updated_at"] = now()
            if message:
                data["logs"] = [*data.get("logs", []), {"time": now(), "message": message}][-100:]
            c.execute("UPDATE jobs SET status=?,data=? WHERE id=?", (data["status"], json.dumps(data), ident))
            return data

    def claim(self):
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT data FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
            if not row:
                return None
            job = json.loads(row[0])
            job.update(status="preparing", stage="Preparando arquivos", updated_at=now())
            c.execute("UPDATE jobs SET status=?,data=? WHERE id=?", (job["status"], json.dumps(job), job["id"]))
            return job

    def recover(self, *, local_only=False):
        # Never resubmit automatically after an uncertain, potentially billed submission.
        for job in self.jobs():
            if local_only and job["status"] in ACTIVE and job.get("settings", {}).get("engine") != "comfy-local":
                self.update_job(job["id"], status="failed", stage="Versão anterior", error="Esta tarefa pertence ao motor anterior e não será reenviada. Crie uma geração com o motor local.", message="Migração para modo local: tarefas antigas não são retomadas nem cobradas.")
                continue
            if job["status"] not in ACTIVE or job["status"] == "queued":
                continue
            if job.get("settings", {}).get("engine") == "comfy-local":
                self.update_job(job["id"], status="failed", stage="Interrompido", error="O aplicativo reiniciou durante a geração local. Confira o ComfyUI antes de gerar novamente.", message="A geração local não foi reenviada automaticamente.")
                continue
            if job.get("provider_request_id"):
                self.update_job(job["id"], status="queued", stage="Retomando consulta ao provedor", message="Servidor reiniciado; a tarefa remota será consultada sem reenviar.")
            else:
                self.update_job(job["id"], status="failed", stage="Interrompido", error="O servidor reiniciou durante a preparação ou envio. Confira o painel do provedor antes de gerar novamente; a cobrança remota pode ter ocorrido.", message="Tarefa interrompida; reenvio automático desativado para evitar cobrança duplicada.")

    def remove_job(self, ident):
        with self.connection() as c:
            c.execute("DELETE FROM jobs WHERE id=?", (ident,))
