from __future__ import annotations

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import ipaddress
import json
import secrets
import threading
from uuid import uuid4
from zoneinfo import available_timezones

import uvicorn
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import ROOT_DIR, load_config
from app.models import Dashboard, SettingsUpdate
from app.services.runtime import RuntimeService
from app.services.spl_reports import SPLReportStore
from app.services.planning_center import PlanningCenterClient
from app.services.propresenter import ProPresenterClient
from app.services.restream import RestreamClient
from app.services.thelightingcontroller import TheLightingControllerClient
from app.store import ConfigStore
from app.update import download_update, update_status
from app.version import __version__


class ActivePlanRequest(BaseModel):
    id: str | None = None
    service_type_id: str | None = None


class OSMMeasurement(BaseModel):
    laeq: float | None = None
    lceq: float | None = None
    lzeq: float | None = None
    peak: float | None = None
    fast: float | None = None
    slow: float | None = None
    a_fast: float | None = None
    a_slow: float | None = None
    b_fast: float | None = None
    b_slow: float | None = None
    c_fast: float | None = None
    c_slow: float | None = None
    z_fast: float | None = None
    z_slow: float | None = None
    timestamp: str | None = None


class ProPresenterSlideTrigger(BaseModel):
    index: int
    presentation_uuid: str | None = None
    playlist_index: int | None = None
    is_pco: bool = False
    dashboard_slug: str | None = None
    widget_id: str | None = None


class ProPresenterNavigationRequest(BaseModel):
    dashboard_slug: str | None = None
    widget_id: str | None = None


class LightingButtonTrigger(BaseModel):
    name: str
    mode: str = "toggle"
    dashboard_slug: str | None = None
    widget_id: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_config()
    store = ConfigStore(config.data_file)
    runtime = RuntimeService(store, SPLReportStore(config.data_file.with_name("spl-samples.jsonl")))
    app.state.instance_id = uuid4().hex
    app.state.store = store
    app.state.runtime = runtime
    await runtime.start()
    try:
        yield
    finally:
        await runtime.close()


app = FastAPI(title="ChurchBoard", version=__version__, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=ROOT_DIR / "app" / "static"), name="static")


@app.middleware("http")
async def prevent_stale_dashboard_assets(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path in {"/admin", "/desktop"} or request.url.path.startswith(("/display/", "/editor/")):
        response.headers["Cache-Control"] = "no-store"
    return response


def store_from(request: Request) -> ConfigStore:
    return request.app.state.store


def dashboard_or_404(store: ConfigStore, identifier: str) -> dict:
    dashboard = next((item for item in store.load()["dashboards"] if item["id"] == identifier or item["slug"] == identifier), None)
    if not dashboard:
        raise HTTPException(404, "Dashboard not found")
    return dashboard


@app.get("/")
async def root() -> RedirectResponse:
    return RedirectResponse("/desktop")


@app.get("/desktop")
async def desktop_page() -> FileResponse:
    return FileResponse(ROOT_DIR / "app" / "static" / "desktop.html")


@app.get("/admin")
async def admin_page() -> FileResponse:
    return FileResponse(ROOT_DIR / "app" / "static" / "admin.html")


@app.get("/display/{slug}")
async def display_page(slug: str) -> FileResponse:
    return FileResponse(ROOT_DIR / "app" / "static" / "display.html")


@app.get("/editor/{slug}")
async def editor_page(slug: str) -> FileResponse:
    return FileResponse(ROOT_DIR / "app" / "static" / "editor.html")


@app.get("/api/dashboards")
async def list_dashboards(request: Request) -> dict:
    return {"items": store_from(request).load()["dashboards"]}


@app.get("/api/dashboards/{identifier}")
async def get_dashboard(identifier: str, request: Request) -> dict:
    return dashboard_or_404(store_from(request), identifier)


@app.post("/api/dashboards", status_code=201)
async def create_dashboard(payload: Dashboard, request: Request) -> dict:
    store = store_from(request)
    data = store.load()
    if any(item["id"] == payload.id or item["slug"] == payload.slug for item in data["dashboards"]):
        raise HTTPException(409, "Dashboard ID and URL must be unique")
    dashboard = payload.model_dump()
    data["dashboards"].append(dashboard)
    store.save(data)
    return dashboard


@app.put("/api/dashboards/{identifier}")
async def update_dashboard(identifier: str, payload: Dashboard, request: Request) -> dict:
    store = store_from(request)
    data = store.load()
    index = next((i for i, item in enumerate(data["dashboards"]) if item["id"] == identifier or item["slug"] == identifier), None)
    if index is None:
        raise HTTPException(404, "Dashboard not found")
    if any(i != index and (item["id"] == payload.id or item["slug"] == payload.slug) for i, item in enumerate(data["dashboards"])):
        raise HTTPException(409, "Dashboard ID and URL must be unique")
    data["dashboards"][index] = payload.model_dump()
    store.save(data)
    return data["dashboards"][index]


@app.delete("/api/dashboards/{identifier}", status_code=204)
async def delete_dashboard(identifier: str, request: Request) -> None:
    store = store_from(request)
    data = store.load()
    original = len(data["dashboards"])
    data["dashboards"] = [item for item in data["dashboards"] if item["id"] != identifier and item["slug"] != identifier]
    if len(data["dashboards"]) == original:
        raise HTTPException(404, "Dashboard not found")
    if not data["dashboards"]:
        raise HTTPException(400, "ChurchBoard must have at least one dashboard")
    store.save(data)


@app.get("/api/settings")
async def get_settings(request: Request) -> dict:
    return store_from(request).public_settings()


@app.put("/api/settings")
async def update_settings(payload: SettingsUpdate, request: Request) -> dict:
    store = store_from(request)
    data = store.load()
    settings = payload.model_dump()
    existing_secret = data["settings"].get("planning_center", {}).get("secret", "")
    if not settings.get("planning_center", {}).get("secret"):
        settings.setdefault("planning_center", {})["secret"] = existing_secret
    existing_restream = data["settings"].get("restream", {})
    for secret_name in ("client_secret", "access_token", "refresh_token"):
        if not settings.get("restream", {}).get(secret_name):
            settings.setdefault("restream", {})[secret_name] = existing_restream.get(secret_name, "")
    if not settings.get("obs", {}).get("password"):
        settings.setdefault("obs", {})["password"] = data["settings"].get("obs", {}).get("password", "")
    if not settings.get("lighting", {}).get("password"):
        settings.setdefault("lighting", {})["password"] = data["settings"].get("lighting", {}).get("password", "")
    data["settings"] = settings
    store.save(data)
    await request.app.state.runtime.refresh(force=True)
    return store.public_settings()


@app.get("/api/runtime")
async def get_runtime(request: Request, compact: bool = False) -> dict:
    state = deepcopy(request.app.state.runtime.state)
    if not compact:
        return state

    # ProPresenter is polled quickly, while the Planning Center plan, people,
    # photos, and media catalog change slowly and are cached by the display.
    timing = state.get("timing") or {}
    timing.pop("service_items", None)
    propresenter = state.get("propresenter") or {}
    propresenter.pop("playlist_presentations", None)
    propresenter.pop("slides", None)
    payload = {
        key: state.get(key)
        for key in (
            "updated_at",
            "timing",
            "mics",
            "propresenter",
            "planning_center_live",
            "service_control",
            "osm",
            "restream",
            "obs",
        )
    }
    payload["propresenter"] = propresenter
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    etag = f'"{sha256(encoded).hexdigest()}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(encoded, media_type="application/json", headers={"ETag": etag})


@app.post("/api/integrations/osm/measurement", status_code=202)
async def ingest_osm_measurement(payload: OSMMeasurement, request: Request) -> dict:
    measurement = payload.model_dump(exclude_none=True)
    if not any(key in measurement for key in ("laeq", "lceq", "lzeq", "peak", "fast", "slow", "a_fast", "a_slow", "b_fast", "b_slow", "c_fast", "c_slow", "z_fast", "z_slow")):
        raise HTTPException(400, "Measurement does not contain an SPL level")
    runtime = request.app.state.runtime
    runtime.record_spl_measurement(measurement)
    runtime.state["osm"] = {"connected": True, "last_measurement_at": measurement.get("timestamp"), **measurement}
    return {"accepted": True}


@app.post("/api/integrations/osm/test")
async def test_osm_connection(request: Request) -> dict:
    settings = store_from(request).load()["settings"].get("open_sound_meter", {})
    if not settings.get("enabled"):
        raise HTTPException(400, "Enable Open Sound Meter monitoring and save settings first")
    osm = request.app.state.runtime.state.get("osm") or {}
    timestamp = str(osm.get("last_measurement_at") or "")
    try:
        age = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(timestamp.replace("Z", "+00:00"))).total_seconds())
    except ValueError:
        age = None
    if osm.get("connected") and age is not None and age <= 3:
        return {"connected": True, "age_seconds": round(age, 1), "message": f"Receiving OSM levels · A Fast {float(osm.get('a_fast', osm.get('laeq'))):.1f} dBA"}
    return {"connected": False, "message": "No recent valid OSM level packet. Confirm OSM Remote API Server and multicast network access."}


@app.get("/api/reports/services")
async def list_spl_report_services(request: Request) -> dict:
    return {"items": request.app.state.runtime.spl_reports.services()}


@app.get("/api/reports/services/{service_id}/spl-averages.csv")
async def download_spl_averages(service_id: str, request: Request) -> PlainTextResponse:
    content = request.app.state.runtime.spl_reports.csv(service_id)
    return PlainTextResponse(content, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="churchboard-{service_id}-spl-averages.csv"'})


@app.get("/api/reports/services/{service_id}/spl-graph.html")
async def download_spl_graph(service_id: str, request: Request) -> Response:
    content = request.app.state.runtime.spl_reports.graph_html(service_id)
    return Response(content, media_type="text/html", headers={"Content-Disposition": f'attachment; filename="churchboard-{service_id}-spl-graph.html"'})


@app.get("/api/app-info")
async def get_app_info(request: Request) -> dict:
    return {
        "instance_id": request.app.state.instance_id,
        "version": request.app.version,
        "desktop_tray": bool(getattr(request.app.state, "desktop_tray", False)),
        "macos_launchservices": bool(getattr(request.app.state, "macos_launchservices", False)),
    }


def require_local_desktop(request: Request) -> None:
    host = request.client.host if request.client else ""
    if host == "testclient":
        return
    try:
        if ipaddress.ip_address(host).is_loopback:
            return
    except ValueError:
        pass
    raise HTTPException(403, "Desktop controls are only available on the computer running ChurchBoard")


@app.get("/api/desktop/update")
async def check_desktop_update(request: Request) -> dict:
    require_local_desktop(request)
    result = await update_status()
    result.pop("_asset", None)
    return result


@app.post("/api/desktop/update")
async def install_desktop_update(request: Request) -> dict:
    require_local_desktop(request)
    return await download_update()


@app.post("/api/desktop/quit")
async def quit_desktop(request: Request) -> dict:
    require_local_desktop(request)
    callback = getattr(request.app.state, "desktop_quit", None)
    if not callback:
        raise HTTPException(409, "This ChurchBoard process is not running with a desktop icon")
    threading.Timer(0.3, callback).start()
    return {"stopping": True}


@app.get("/api/timezones")
async def list_timezones() -> dict:
    return {"items": sorted(available_timezones())}


@app.post("/api/runtime/refresh")
async def refresh_runtime(request: Request) -> dict:
    return await request.app.state.runtime.refresh(force=True)


@app.put("/api/active-plan")
async def select_active_plan(payload: ActivePlanRequest, request: Request) -> dict:
    store = store_from(request)
    data = store.load()
    data["settings"]["manual_plan"] = (
        {"id": payload.id, "service_type_id": payload.service_type_id}
        if payload.id and payload.service_type_id
        else None
    )
    store.save(data)
    return await request.app.state.runtime.refresh(force=True)


@app.post("/api/service-control/{action}")
async def service_control(action: str, request: Request) -> dict:
    try:
        return await request.app.state.runtime.service_control(action)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/integrations/planning-center/test")
async def test_planning_center(request: Request) -> dict:
    settings = store_from(request).load()["settings"].get("planning_center", {})
    client = PlanningCenterClient(settings)
    if not client.configured:
        raise HTTPException(400, "Enable Planning Center and save both the Application ID and secret first")
    try:
        service_types = await client.service_types()
    except Exception as exc:
        raise HTTPException(502, f"Planning Center connection failed: {exc}") from exc
    return {"connected": True, "items": service_types, "count": len(service_types)}


@app.post("/api/integrations/restream/test")
async def test_restream(request: Request) -> dict:
    client = RestreamClient(store_from(request).load()["settings"].get("restream", {}))
    try:
        return await client.test_connection()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(exc.response.status_code, "Restream rejected the access token") from exc
    except Exception as exc:
        raise HTTPException(502, f"Restream connection failed: {exc}") from exc
    finally:
        await client.close()


@app.get("/api/integrations/lighting/buttons")
async def lighting_buttons(request: Request) -> dict:
    client = TheLightingControllerClient(store_from(request).load()["settings"].get("lighting", {}))
    if not client.configured:
        raise HTTPException(400, "Enable lighting control and save its computer address first")
    try:
        buttons = await client.buttons()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not read lighting controls: {exc}") from exc
    return {"connected": True, "items": buttons, "count": len(buttons)}


def require_lighting_widget_control(request: Request, dashboard_slug: str | None, widget_id: str | None) -> dict:
    data = store_from(request).load()
    dashboard = next((item for item in data.get("dashboards", []) if str(item.get("slug") or "") == str(dashboard_slug or "")), None)
    widget = next((item for item in (dashboard or {}).get("widgets", []) if str(item.get("id") or "") == str(widget_id or "")), None)
    if not widget or widget.get("type") != "lighting" or widget.get("settings", {}).get("allow_remote_trigger") is False:
        raise HTTPException(403, "Lighting triggering is disabled in this widget's settings")
    return data["settings"].get("lighting", {})


@app.post("/api/integrations/lighting/button")
async def lighting_trigger_button(payload: LightingButtonTrigger, request: Request) -> dict:
    settings = require_lighting_widget_control(request, payload.dashboard_slug, payload.widget_id)
    client = TheLightingControllerClient(settings)
    if not client.configured:
        raise HTTPException(400, "Lighting control is not connected")
    try:
        await client.trigger_button(payload.name, payload.mode)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not trigger lighting button: {exc}") from exc
    return {"ok": True, "name": payload.name, "mode": payload.mode}


RESTREAM_CALLBACK_PATH = "/api/integrations/restream/callback"


@app.get("/api/integrations/restream/connect")
async def connect_restream(request: Request) -> RedirectResponse:
    settings = store_from(request).load()["settings"].get("restream", {})
    if not settings.get("client_id") or not settings.get("client_secret"):
        raise HTTPException(400, "Save the Restream Client ID and Client Secret first")
    state = secrets.token_urlsafe(32)
    request.app.state.restream_oauth_state = state
    callback = str(request.base_url).rstrip("/") + RESTREAM_CALLBACK_PATH
    from urllib.parse import urlencode
    query = urlencode({"response_type": "code", "client_id": settings["client_id"], "redirect_uri": callback, "state": state})
    return RedirectResponse(f"https://api.restream.io/login?{query}")


@app.get(RESTREAM_CALLBACK_PATH)
async def restream_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    expected_state = getattr(request.app.state, "restream_oauth_state", "")
    request.app.state.restream_oauth_state = ""
    if not code:
        return RedirectResponse("/admin?restream=denied")
    if not expected_state or not secrets.compare_digest(state, expected_state):
        raise HTTPException(400, "Invalid Restream OAuth state; please try connecting again")
    store = store_from(request)
    data = store.load()
    restream = data["settings"].get("restream", {})
    client = RestreamClient(restream)
    try:
        token = await client.exchange_code(code, str(request.base_url).rstrip("/") + RESTREAM_CALLBACK_PATH)
    except Exception as exc:
        raise HTTPException(502, f"Restream authorization failed: {exc}") from exc
    finally:
        await client.close()
    restream.update({"enabled": True, "access_token": token.get("access_token") or token.get("accessToken") or "", "refresh_token": token.get("refresh_token") or token.get("refreshToken") or "", "access_token_expires_at": token.get("expires") or token.get("accessTokenExpiresEpoch") or 0})
    data["settings"]["restream"] = restream
    store.save(data)
    await request.app.state.runtime.refresh(force=True)
    return RedirectResponse("/admin?restream=connected")


@app.get("/api/integrations/planning-center/catalog")
async def planning_center_catalog(request: Request) -> dict:
    app_settings = store_from(request).load()["settings"]
    if app_settings.get("demo_mode"):
        teams = [
            {"id": "band", "name": "Band", "service_type_id": "demo", "service_type_name": "Sunday Worship", "positions": [
                {"id": "demo-1", "name": "Vox 1", "key": "band::vox 1"},
                {"id": "demo-2", "name": "Vox 2", "key": "band::vox 2"},
                {"id": "demo-3", "name": "Worship Leader", "key": "band::worship leader"},
            ]},
            {"id": "production", "name": "Production", "service_type_id": "demo", "service_type_name": "Sunday Worship", "positions": [
                {"id": "demo-4", "name": "Audio", "key": "production::audio"},
                {"id": "demo-5", "name": "Lighting", "key": "production::lighting"},
                {"id": "demo-6", "name": "ProPresenter", "key": "production::propresenter"},
            ]},
            {"id": "speaking", "name": "Speaking", "service_type_id": "demo", "service_type_name": "Sunday Worship", "positions": [
                {"id": "demo-7", "name": "Pastor", "key": "speaking::pastor"},
            ]},
        ]
        return {"items": teams, "count": 7, "demo": True}
    settings = app_settings.get("planning_center", {})
    client = PlanningCenterClient(settings)
    if not client.configured:
        raise HTTPException(400, "Connect Planning Center in Setup to load teams and positions")
    try:
        teams = await client.position_catalog()
    except Exception as exc:
        raise HTTPException(502, f"Could not load Planning Center positions: {exc}") from exc
    return {"items": teams, "count": sum(len(team["positions"]) for team in teams)}


@app.get("/api/integrations/propresenter/thumbnail/{presentation_uuid}/{index}")
async def propresenter_thumbnail(presentation_uuid: str, index: int, request: Request) -> Response:
    settings = store_from(request).load()["settings"].get("propresenter", {})
    client = ProPresenterClient(settings)
    if not client.configured:
        raise HTTPException(400, "ProPresenter is not connected")
    try:
        content, media_type = await client.thumbnail(presentation_uuid, index)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not load the ProPresenter slide image: {exc}") from exc
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, max-age=2"})


def require_propresenter_widget_control(request: Request, dashboard_slug: str | None, widget_id: str | None) -> dict:
    data = store_from(request).load()
    dashboard = next(
        (item for item in data.get("dashboards", []) if str(item.get("slug") or "") == str(dashboard_slug or "")),
        None,
    )
    widget = next(
        (item for item in (dashboard or {}).get("widgets", []) if str(item.get("id") or "") == str(widget_id or "")),
        None,
    )
    if not widget or widget.get("type") != "playlist" or widget.get("settings", {}).get("allow_remote_trigger") is False:
        raise HTTPException(403, "Enable ProPresenter triggering in this Playlist widget's settings")
    return data["settings"].get("propresenter", {})


@app.post("/api/integrations/propresenter/active-slide")
async def propresenter_trigger_active_slide(payload: ProPresenterSlideTrigger, request: Request) -> dict:
    settings = require_propresenter_widget_control(request, payload.dashboard_slug, payload.widget_id)
    client = ProPresenterClient(settings)
    if not client.configured:
        raise HTTPException(400, "ProPresenter is not connected")
    try:
        if payload.presentation_uuid and payload.playlist_index is not None:
            await client.trigger_playlist_slide(payload.playlist_index, payload.presentation_uuid, payload.index, payload.is_pco)
        elif payload.presentation_uuid:
            await client.trigger_presentation_slide(payload.presentation_uuid, payload.index)
        else:
            await client.trigger_active_slide(payload.index)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not trigger the ProPresenter slide: {exc}") from exc
    finally:
        await client.close()
    return {"ok": True, "index": payload.index + 1}


@app.post("/api/integrations/propresenter/navigate/{direction}")
async def propresenter_navigate(direction: str, request: Request, payload: ProPresenterNavigationRequest | None = None) -> dict:
    settings = require_propresenter_widget_control(request, payload.dashboard_slug if payload else None, payload.widget_id if payload else None)
    client = ProPresenterClient(settings)
    if not client.configured:
        raise HTTPException(400, "ProPresenter is not connected")
    try:
        await client.trigger_navigation(direction)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not move ProPresenter {direction}: {exc}") from exc
    finally:
        await client.close()
    return {"ok": True, "direction": direction}


@app.get("/api/integrations/propresenter/playlist-diagnostics")
async def propresenter_playlist_diagnostics(request: Request) -> dict:
    settings = store_from(request).load()["settings"].get("propresenter", {})
    client = ProPresenterClient(settings)
    if not client.configured:
        raise HTTPException(400, "ProPresenter is not connected")
    try:
        return await client.playlist_diagnostics()
    except Exception as exc:
        raise HTTPException(502, f"Could not read the ProPresenter playlist diagnostics: {exc}") from exc
    finally:
        await client.close()


@app.post("/api/integrations/propresenter/active-playlist-item")
async def propresenter_trigger_active_playlist_item(payload: ProPresenterSlideTrigger, request: Request) -> dict:
    settings = require_propresenter_widget_control(request, payload.dashboard_slug, payload.widget_id)
    client = ProPresenterClient(settings)
    if not client.configured:
        raise HTTPException(400, "ProPresenter is not connected")
    try:
        await client.trigger_playlist_presentation(payload.index, None if payload.is_pco else payload.presentation_uuid)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Could not trigger the ProPresenter playlist item: {exc}") from exc
    finally:
        await client.close()
    return {"ok": True, "index": payload.index + 1}


def run() -> None:
    config = load_config()
    uvicorn.run("app.main:app", host=config.host, port=config.port, reload=False)
