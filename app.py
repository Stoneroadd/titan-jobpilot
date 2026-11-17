"""Local-first job application organizer and reviewed browser autofill."""
from __future__ import annotations

import csv
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("JOBPILOT_DATA_DIR", ROOT / "data"))
PRIVATE = DATA / "private"
PROFILE_FILE = PRIVATE / "profile.json"
JOBS_FILE = PRIVATE / "jobs.json"
ALLOWED_RESUME = {"pdf", "docx"}
MAX_RESUME_BYTES = 10 * 1024 * 1024
app = Flask(__name__)
app.secret_key = os.environ.get("JOBPILOT_SECRET", secrets.token_urlsafe(32))
app.config["MAX_CONTENT_LENGTH"] = MAX_RESUME_BYTES + 1024 * 1024
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


@app.context_processor
def inject_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["_csrf_token"]}


@app.before_request
def protect_local_forms():
    if request.method == "POST":
        expected = session.get("_csrf_token", "")
        received = request.form.get("csrf_token", "")
        if not expected or not hmac.compare_digest(expected, received):
            abort(400, description="Formulario expirado o token CSRF inválido. Recarga el panel.")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def get_profile() -> dict:
    return load_json(PROFILE_FILE, {})


def get_jobs() -> list[dict]:
    jobs = load_json(JOBS_FILE, [])
    return jobs if isinstance(jobs, list) else []


def normalize_url(value: str) -> str:
    return value.strip().rstrip("/").lower()


def parse_skills(value: str) -> list[str]:
    return sorted({item.strip().casefold() for item in re.split(r"[,;\n]", value) if item.strip()})


def match_score(job: dict, profile: dict) -> tuple[int, list[str]]:
    wanted = set(parse_skills(job.get("skills", "")))
    candidate = set(parse_skills(profile.get("skills", "")))
    overlap = sorted(wanted & candidate)
    return (round(100 * len(overlap) / len(wanted)) if wanted else 0, overlap)


def valid_http_url(value: str) -> bool:
    return value.startswith(("https://", "http://"))


def append_job(job: dict) -> bool:
    jobs = get_jobs()
    application_url = normalize_url(job.get("application_url", ""))
    key = (job.get("company", "").strip().casefold(), job.get("title", "").strip().casefold())
    if application_url and any(normalize_url(item.get("application_url", "")) == application_url for item in jobs):
        return False
    if key != ("", "") and any((item.get("company", "").strip().casefold(), item.get("title", "").strip().casefold()) == key for item in jobs):
        return False
    job.update({"id": uuid.uuid4().hex[:10], "status": "new", "created_at": datetime.now(timezone.utc).isoformat()})
    jobs.append(job)
    save_json(JOBS_FILE, jobs)
    return True


@app.get("/")
def home():
    profile = get_profile()
    jobs = get_jobs()
    for job in jobs:
        job["match_score"], job["matched_skills"] = match_score(job, profile)
    jobs.sort(key=lambda item: (item["status"] == "applied", -item["match_score"], item.get("company", "").casefold()))
    resume = profile.get("resume_file", "")
    return render_template("index.html", profile=profile, jobs=jobs,
                           has_resume=bool(resume and (PRIVATE / resume).is_file()),
                           total=len(jobs), queued=sum(job["status"] == "queued" for job in jobs),
                           applied=sum(job["status"] == "applied" for job in jobs))


@app.post("/profile")
def update_profile():
    profile = {key: request.form.get(key, "").strip() for key in
               ("full_name", "email", "phone", "location", "skills", "linkedin", "portfolio")}
    if profile["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", profile["email"]):
        flash("Revisa el formato del correo electrónico.", "error")
        return redirect(url_for("home") + "#profile")
    old = get_profile()
    profile["resume_file"] = old.get("resume_file", "")
    save_json(PROFILE_FILE, profile)
    flash("Perfil guardado solo en este equipo.", "success")
    return redirect(url_for("home") + "#profile")


@app.post("/resume")
def upload_resume():
    file = request.files.get("resume")
    if not file or not file.filename:
        flash("Selecciona un CV PDF o DOCX.", "error")
        return redirect(url_for("home") + "#profile")
    suffix = Path(secure_filename(file.filename)).suffix.lower().lstrip(".")
    if suffix not in ALLOWED_RESUME:
        flash("Formato no admitido. Usa PDF o DOCX.", "error")
        return redirect(url_for("home") + "#profile")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    destination = PRIVATE / f"resume.{suffix}"
    file.save(destination)
    if destination.stat().st_size > MAX_RESUME_BYTES:
        destination.unlink(missing_ok=True)
        flash("El archivo supera el límite de 10 MB.", "error")
        return redirect(url_for("home") + "#profile")
    profile = get_profile()
    profile["resume_file"] = destination.name
    save_json(PROFILE_FILE, profile)
    flash("CV guardado localmente; nunca se copia al repositorio.", "success")
    return redirect(url_for("home") + "#profile")


@app.post("/jobs")
def add_job():
    job = {key: request.form.get(key, "").strip() for key in
           ("title", "company", "location", "application_url", "description", "skills")}
    if not job["title"] or not job["company"]:
        flash("El cargo y la empresa son obligatorios.", "error")
        return redirect(url_for("home") + "#offers")
    if job["application_url"] and not valid_http_url(job["application_url"]):
        flash("La URL de postulación debe comenzar con http:// o https://.", "error")
        return redirect(url_for("home") + "#offers")
    if append_job(job):
        flash("Oferta añadida a tu lista local.", "success")
    else:
        flash("La oferta parece duplicada por URL o empresa y cargo.", "error")
    return redirect(url_for("home") + "#offers")


@app.post("/jobs/import")
def import_jobs():
    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("Selecciona un CSV para importar ofertas.", "error")
        return redirect(url_for("home") + "#offers")
    try:
        content = file.stream.read(2_000_001).decode("utf-8-sig")
        if len(content) > 2_000_000:
            raise ValueError("CSV demasiado grande (máx. 2 MB).")
        reader = csv.DictReader(content.splitlines())
        required = {"title", "company"}
        if not reader.fieldnames or not required.issubset({name.strip().lower() for name in reader.fieldnames}):
            raise ValueError("El CSV requiere encabezados title y company.")
        count = 0
        for raw in reader:
            row = {str(key).strip().lower(): (value or "").strip() for key, value in raw.items() if key}
            job = {field: row.get(field, "") for field in ("title", "company", "location", "application_url", "description", "skills")}
            if job["title"] and job["company"] and (not job["application_url"] or valid_http_url(job["application_url"])):
                count += int(append_job(job))
        flash(f"Se importaron {count} oferta(s) nueva(s). Las duplicadas se omitieron.", "success")
    except (UnicodeDecodeError, csv.Error, ValueError) as error:
        flash(f"No se pudo leer el CSV: {error}", "error")
    return redirect(url_for("home") + "#offers")


@app.post("/jobs/<job_id>/status")
def change_status(job_id: str):
    status = request.form.get("status", "")
    if status not in {"new", "queued", "applied", "skipped"}:
        flash("Estado desconocido.", "error")
        return redirect(url_for("home") + "#offers")
    jobs = get_jobs()
    for job in jobs:
        if job["id"] == job_id:
            job["status"] = status
            job["updated_at"] = datetime.now(timezone.utc).isoformat()
            save_json(JOBS_FILE, jobs)
            flash("Estado actualizado localmente.", "success")
            break
    return redirect(url_for("home") + "#offers")


@app.post("/jobs/<job_id>/autofill")
def launch_autofill(job_id: str):
    profile = get_profile()
    job = next((item for item in get_jobs() if item["id"] == job_id), None)
    if not job:
        flash("No se encontró la oferta.", "error")
        return redirect(url_for("home") + "#offers")
    required = (profile.get("full_name"), profile.get("email"), profile.get("resume_file"))
    if not all(required) or not (PRIVATE / Path(profile.get("resume_file", "")).name).is_file():
        flash("Completa nombre, email y carga un CV antes de preparar la postulación.", "error")
        return redirect(url_for("home") + "#profile")
    if not job.get("application_url"):
        flash("Añade la URL oficial del formulario de esta oferta.", "error")
        return redirect(url_for("home") + "#offers")
    if job["status"] == "applied":
        flash("Esta oferta ya está marcada como postulada; evita duplicar el envío.", "error")
        return redirect(url_for("home") + "#offers")
    try:
        subprocess.Popen([sys.executable, str(ROOT / "autofill.py"), "--job-id", job_id],
                         cwd=str(ROOT), close_fds=True)
        flash("Navegador abierto para rellenar y revisar. El agente no pulsa Enviar.", "success")
    except OSError as error:
        flash(f"No se pudo iniciar el navegador automatizado: {error}", "error")
    return redirect(url_for("home") + "#offers")


@app.post("/jobs/prepare-queue")
def launch_queue():
    profile = get_profile()
    resume = PRIVATE / Path(profile.get("resume_file", "")).name
    if not profile.get("full_name") or not profile.get("email") or not resume.is_file():
        flash("Completa nombre, email y carga un CV antes de preparar postulaciones.", "error")
        return redirect(url_for("home") + "#profile")
    queued = [job for job in get_jobs() if job.get("status") == "queued" and job.get("application_url")]
    if not queued:
        flash("Marca ofertas como En revisión y añade su URL oficial antes de preparar la cola.", "error")
        return redirect(url_for("home") + "#offers")
    try:
        subprocess.Popen([sys.executable, str(ROOT / "autofill.py"), "--all-queued"],
                         cwd=str(ROOT), close_fds=True)
        flash(f"Se abrirá la cola de {len(queued)} oferta(s), una a la vez. Revisa cada formulario y envíalo manualmente si corresponde.", "success")
    except OSError as error:
        flash(f"No se pudo iniciar la cola automatizada: {error}", "error")
    return redirect(url_for("home") + "#offers")


@app.errorhandler(413)
def request_too_large(_error):
    flash("El archivo supera el límite permitido.", "error")
    return redirect(url_for("home") + "#profile")


if __name__ == "__main__":
    PRIVATE.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=int(os.environ.get("JOBPILOT_PORT", "5055")), debug=False)
