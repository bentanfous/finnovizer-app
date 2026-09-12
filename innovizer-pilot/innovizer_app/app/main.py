"""
Innovizer Pilot — API HTTP (FastAPI).

Un seul service expose toute la chaîne :

    POST /api/jobs                      créer un dossier
    GET  /api/jobs                      lister
    GET  /api/jobs/{id}                 état + inventaire des fichiers
    POST /api/jobs/{id}/files          uploader un fichier (catégorie)
    POST /api/jobs/{id}/build          construire le Data Hub (B01 + B02)
    GET  /api/jobs/{id}/hub            résumé du Data Hub
    GET  /api/jobs/{id}/projects       projets à instruire
    GET  /api/jobs/{id}/projects/{c}   contexte d'un projet
    POST /api/jobs/{id}/interviews     ouvrir un entretien Eva
    POST /api/interviews/{id}/answer   répondre
    POST /api/interviews/{id}/finalize finaliser -> fiche projet
    GET  /api/jobs/{id}/export         télécharger brique01.xlsx
    GET  /api/health

Le frontend statique est servi à la racine.
"""

from pathlib import Path

from fastapi import FastAPI, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .settings import VERSION, MAX_UPLOAD_MB, DERIVED_DIR
from .jobs import STORE, CATEGORIES

app = FastAPI(title="Innovizer Pilot", version=VERSION)

WEB = Path(__file__).parent.parent / "web"

# état d'entretien -> job, pour router /interviews/{id}
_INTERVIEW_JOB: dict[str, str] = {}


@app.get("/api/health")
def health():
    return {"ok": True, "version": VERSION, "jobs": len(STORE.lister())}


class CreerJob(BaseModel):
    client: str = ""
    exercice: int = 2025


@app.post("/api/jobs")
def creer_job(body: CreerJob):
    j = STORE.creer(body.client, body.exercice)
    return j.meta()


@app.get("/api/jobs")
def lister_jobs():
    return {"jobs": STORE.lister()}


@app.get("/api/jobs/{jid}")
def etat_job(jid: str):
    try:
        return STORE.get(jid).meta()
    except KeyError:
        raise HTTPException(404, "dossier inconnu")


@app.post("/api/jobs/{jid}/files")
async def upload(jid: str, categorie: str = Form(...), fichier: UploadFile = None):
    try:
        j = STORE.get(jid)
    except KeyError:
        raise HTTPException(404, "dossier inconnu")
    if categorie not in CATEGORIES:
        raise HTTPException(400, f"catégorie inconnue (attendu : {CATEGORIES})")
    if fichier is None:
        raise HTTPException(400, "aucun fichier")
    contenu = await fichier.read()
    if len(contenu) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"fichier > {MAX_UPLOAD_MB} Mo")
    j.ajouter_fichier(categorie, fichier.filename, contenu)
    return {"ok": True, "inventaire": j.inventaire()}


class BuildBody(BaseModel):
    arbitrages: dict = {}


@app.post("/api/jobs/{jid}/build")
def build(jid: str, body: BuildBody = BuildBody()):
    try:
        j = STORE.get(jid)
    except KeyError:
        raise HTTPException(404, "dossier inconnu")
    try:
        return j.construire_data_hub(body.arbitrages)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"échec construction : {type(e).__name__}: {e}")


@app.get("/api/jobs/{jid}/hub")
def hub(jid: str):
    p = DERIVED_DIR / jid / "data_hub.json"
    if not p.exists():
        raise HTTPException(404, "Data Hub non construit — appeler /build")
    import json
    return json.loads(p.read_text())


@app.get("/api/jobs/{jid}/projects")
def projects(jid: str):
    try:
        j = STORE.get(jid)
    except KeyError:
        raise HTTPException(404, "dossier inconnu")
    if j._b01 is None:
        j.construire_data_hub()
    return {"projets": j.projets()}


@app.get("/api/jobs/{jid}/projects/{code}")
def contexte(jid: str, code: str):
    j = STORE.get(jid)
    if j._b01 is None:
        j.construire_data_hub()
    try:
        return j.contexte_projet(code)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(404, str(e))


class OuvrirEntretien(BaseModel):
    code_projet: str
    regime: str = "A_DETERMINER"
    interlocuteur: str = ""


@app.post("/api/jobs/{jid}/interviews")
def ouvrir(jid: str, body: OuvrirEntretien):
    j = STORE.get(jid)
    if j._b01 is None:
        j.construire_data_hub()
    res = j.ouvrir_entretien(body.code_projet, body.regime, body.interlocuteur)
    _INTERVIEW_JOB[res["id"]] = jid
    return res


class Reponse(BaseModel):
    reponse: str


@app.post("/api/interviews/{eid}/answer")
def repondre(eid: str, body: Reponse):
    jid = _INTERVIEW_JOB.get(eid)
    if not jid:
        raise HTTPException(404, "entretien inconnu")
    return STORE.get(jid).repondre(eid, body.reponse)


@app.post("/api/interviews/{eid}/finalize")
def finaliser(eid: str):
    jid = _INTERVIEW_JOB.get(eid)
    if not jid:
        raise HTTPException(404, "entretien inconnu")
    return STORE.get(jid).finaliser(eid)


@app.get("/api/jobs/{jid}/export")
def export(jid: str):
    p = DERIVED_DIR / jid / "brique01.xlsx"
    if not p.exists():
        raise HTTPException(404, "export indisponible — construire le Data Hub")
    return FileResponse(p, filename=f"innovizer_{jid}.xlsx")


# ------------------------------------------------------------ frontend

if WEB.exists():
    app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    f = WEB / "index.html"
    return f.read_text(encoding="utf-8") if f.exists() else "<h1>Innovizer Pilot</h1>"
