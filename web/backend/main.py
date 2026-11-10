import asyncio
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from backend.catalog import ROOT, SNAPSHOT, CATALOG, CATEGORIES, FOUNDATION, FOCUS_AREAS, course_info
from backend.defaults import default_cards
from backend.llm import available_models, parse_preference, ModelError
from backend.nusmods import build_timetable, planner_export
from backend.schemas import ParseRequest, PlanRequest, TimetableRequest, ExportRequest
from backend.solver import generate_plan, SolverError
from backend.validation import academic_audit
from backend.chat import ChatRequest, chat_config, chat_models, stream_chat
from backend.minors import programmes, audit_minors

app = FastAPI(title="NUS CS Course Planner", version="1.0.0")
solver_slots = asyncio.Semaphore(2)
model_slots = asyncio.Semaphore(4)


@app.middleware("http")
async def local_api_boundary(request: Request, call_next):
    # JSON mutations are same-origin. No permissive CORS or public key endpoint.
    origin = request.headers.get("origin")
    if request.method == "POST" and origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        return JSONResponse({"detail": "Cross-origin API requests are not allowed"}, status_code=403)
    length = request.headers.get("content-length", "0")
    limit = 12 * 1024 * 1024 if request.url.path == '/api/chat' else 262144
    if length.isdigit() and int(length) > limit:
        return JSONResponse({"detail": "Request too large"}, status_code=413)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    if request.url.path in {'/', '/chat'} or request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get("/api/health")
async def health():
    return {"status": "ok", "model_configured": bool(os.getenv("SOCLAAS_API_KEY") and os.getenv("SOCLAAS_MODEL")),
            "model": os.getenv("SOCLAAS_MODEL") or None}


@app.get("/api/config")
async def config():
    return {"schema_version": 1, "catalogue_version":2, "draft_version":3, "defaults": [c.model_dump() for c in default_cards()],
            "catalogue": [course_info(code) for code in CATALOG], "foundation": FOUNDATION,
            "categories":CATEGORIES, "catalogue_updated_at":SNAPSHOT['retrieved_at'],
            "focus_areas": sorted(FOCUS_AREAS), "reference_year": SNAPSHOT["academic_year"],
            "minors": programmes(),
            "degree_source": "https://www.comp.nus.edu.sg/cug/per-cohort/cs/cs-26-27/"}


@app.get("/api/models")
async def models():
    try:
        return {"models": await available_models()}
    except ModelError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/preferences")
async def preferences(request: ParseRequest):
    async with model_slots:
        try:
            return await parse_preference(request)
        except ModelError as exc:
            raise HTTPException(502, str(exc)) from exc


@app.get('/api/chat/config')
async def direct_chat_config():
    return chat_config()


@app.get('/api/chat/models')
async def direct_chat_models():
    try:
        return {'models': await chat_models()}
    except ModelError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post('/api/chat')
async def direct_chat(request: ChatRequest):
    async def events():
        async with model_slots:
            async for item in stream_chat(request):
                yield item
    return StreamingResponse(events(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


@app.post("/api/plans")
async def plans(request: PlanRequest):
    async with solver_slots:
        try:
            result = await asyncio.to_thread(generate_plan, request)
        except SolverError as exc:
            raise HTTPException(503, str(exc)) from exc
    if result["status"] in {"feasible", "conditional"} and result.get('exportable'):
        result["nusmods_planner"] = planner_export(result)
    return result


@app.post('/api/exports/nusmods')
async def export_nusmods(request: ExportRequest):
    audit = academic_audit(request.assignments, math_qualified=request.math_qualified, start_year=request.start_year)
    if audit['status'] != 'passed':
        raise HTTPException(409, {'message': 'Export blocked: foundation, prerequisite or student-profile requirements are not satisfied.',
                                 'academic_audit': audit})
    minor_request = PlanRequest(cards=[{'id': 'minor_' + p, 'title': p, 'rules': [{'type': 'minor_programme', 'programme': p}]} for p in request.minors],
                                horizon=request.horizon, start_year=request.start_year)
    minor_audit = audit_minors(minor_request, request.assignments, request.minor_allocations, request.category_allocations)
    if minor_audit['status'] != 'passed':
        raise HTTPException(409, {'message': 'Export blocked: minor requirements are not satisfied.', 'minor_audit': minor_audit})
    semesters = []
    for number in range(1, request.horizon + 1):
        year = request.start_year + (number - 1) // 2
        semesters.append({'academic_year': f'{year}-{year+1}', 'semester': (number-1) % 2 + 1,
                          'courses': [course_info(c) for c, s in request.assignments.items() if s == number]})
    return JSONResponse(planner_export({'semesters': semesters}), headers={
        'Content-Disposition': 'attachment; filename="pathway-nusmods-planner.json"'})


@app.post("/api/timetable")
async def timetable(request: TimetableRequest):
    return await build_timetable(request)


@app.get("/")
async def index():
    return FileResponse(ROOT / "frontend/index.html")


@app.get('/chat')
async def chat_page():
    return FileResponse(ROOT / 'frontend/chat.html')


app.mount("/static", StaticFiles(directory=ROOT / "frontend"), name="static")
