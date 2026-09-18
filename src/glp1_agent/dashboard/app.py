from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from glp1_agent.config import Settings
from glp1_agent.dashboard.charts import build_trend_chart
from glp1_agent.dashboard.formatting import (
    badge_class,
    humanize,
    local_dt,
    missed_checkin_badge_class,
)
from glp1_agent.dashboard.forms import dt_input_value, resolve_next_dose_at
from glp1_agent.dashboard.messages import ERROR_MESSAGES, SUCCESS_MESSAGES
from glp1_agent.db.connection import create_pool
from glp1_agent.domain.journey_state_machine import IllegalTransitionError, can_transition
from glp1_agent.domain.models import (
    HealthEventSource,
    HealthEventType,
    JourneyState,
    MedicationEventType,
    MetricType,
    SymptomTrend,
)
from glp1_agent.domain.observation_service import build_metric_trends
from glp1_agent.services import Services

_DIR = Path(__file__).parent
templates = Jinja2Templates(directory=_DIR / "templates")
templates.env.filters["humanize"] = humanize
templates.env.filters["badge_class"] = badge_class
templates.env.filters["missed_checkin_badge_class"] = missed_checkin_badge_class
templates.env.filters["local_dt"] = local_dt
templates.env.filters["dt_input"] = dt_input_value
templates.env.filters["trend_chart"] = build_trend_chart

_services: Services | None = None


def services() -> Services:
    assert _services is not None, "Services not initialized — app startup didn't run"
    return _services


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    global _services
    settings = Settings()
    pool = await create_pool(settings.database_url)
    _services = Services.build(pool)
    yield
    await pool.close()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory=_DIR / "static"), name="static")


@app.get("/")
async def list_patients(request: Request):
    patients = await services().dashboard.list_patients()
    return templates.TemplateResponse(request, "patients.html", {"patients": patients})


@app.get("/today")
async def today_metrics(request: Request, for_date: str = ""):
    today = datetime.now(UTC).date()
    selected_date = date.fromisoformat(for_date) if for_date else today
    now = datetime.combine(selected_date, datetime.min.time(), tzinfo=UTC)
    observations = await services().dashboard.get_today_observations(now)
    return templates.TemplateResponse(
        request,
        "today.html",
        {
            "observations": observations,
            "selected_date": selected_date.isoformat(),
            "prev_date": (selected_date - timedelta(days=1)).isoformat(),
            "next_date": (selected_date + timedelta(days=1)).isoformat(),
            "is_today": selected_date == today,
        },
    )


@app.get("/patients/{patient_id}")
async def patient_detail(
    request: Request,
    patient_id: UUID,
    error: str | None = None,
    success: str | None = None,
    tab: str = "record",
    days: str = "",
):
    days_window = int(days) if days else None
    context = await services().patient_context.get_patient_context(patient_id)
    checkin, extraction_items = await services().dashboard.get_last_completed_extraction(patient_id)
    full_record = await services().dashboard.get_full_record(patient_id, days_window)
    metric_trends = build_metric_trends(full_record.observations)
    legal_next_states = [s for s in JourneyState if can_transition(context.journey.state, s)]
    return templates.TemplateResponse(
        request,
        "patient_detail.html",
        {
            "context": context,
            "checkin": checkin,
            "extraction_items": extraction_items,
            "full_record": full_record,
            "metric_trends": metric_trends,
            "journey_states": list(JourneyState),
            "legal_next_states": legal_next_states,
            "symptom_trends": list(SymptomTrend),
            "medication_event_types": list(MedicationEventType),
            "metric_types": list(MetricType),
            "error": ERROR_MESSAGES.get(error, error),
            "success": SUCCESS_MESSAGES.get(success, success),
            "active_tab": tab if tab in ("record", "playground") else "record",
            "selected_days": days_window,
        },
    )


@app.post("/patients/{patient_id}/context/journey")
async def update_journey(
    patient_id: UUID,
    target_state: Annotated[str, Form()],
    reason: Annotated[str, Form()] = "",
):
    try:
        await services().journey.transition(patient_id, JourneyState(target_state), reason or None)
    except IllegalTransitionError:
        return RedirectResponse(
            f"/patients/{patient_id}?error=illegal_transition&tab=playground", status_code=303
        )
    return RedirectResponse(
        f"/patients/{patient_id}?success=journey_updated&tab=playground", status_code=303
    )


@app.post("/patients/{patient_id}/context/medication")
async def update_medication(
    patient_id: UUID,
    dose: Annotated[float, Form()],
    dose_unit: Annotated[str, Form()],
    frequency: Annotated[str, Form()],
    next_dose_at: Annotated[str, Form()] = "",
):
    active = await services().medication_repo.get_active(patient_id)
    if active is None:
        return RedirectResponse(
            f"/patients/{patient_id}?error=no_active_medication&tab=playground", status_code=303
        )
    patient = await services().patient_repo.get(patient_id)
    next_dose_at_value = resolve_next_dose_at(next_dose_at, active.next_dose_at, patient.timezone)
    await services().medication_repo.replace_active(
        active.patient_medication_id, dose, dose_unit, frequency, next_dose_at_value
    )
    return RedirectResponse(
        f"/patients/{patient_id}?success=medication_updated&tab=playground", status_code=303
    )


@app.post("/patients/{patient_id}/context/clinician-instruction")
async def add_clinician_instruction(
    patient_id: UUID,
    metric: Annotated[str, Form()],
    frequency: Annotated[str, Form()],
    instruction: Annotated[str, Form()],
    start_date: Annotated[date, Form()],
    end_date: Annotated[date | None, Form()] = None,
):
    await services().clinician_instructions.create(
        patient_id, metric, frequency, instruction, start_date, end_date
    )
    return RedirectResponse(
        f"/patients/{patient_id}?success=instruction_added&tab=playground", status_code=303
    )


@app.post("/patients/{patient_id}/context/metric-schedule")
async def update_metric_schedule(
    patient_id: UUID,
    metric: Annotated[str, Form()],
    frequency_days: Annotated[int, Form()],
):
    await services().patient_metric_schedules.upsert(patient_id, MetricType(metric), frequency_days)
    return RedirectResponse(
        f"/patients/{patient_id}?success=schedule_updated&tab=playground", status_code=303
    )


@app.post("/patients/{patient_id}/context/health-event")
async def add_health_event(
    patient_id: UUID,
    kind: Annotated[str, Form()],
    occurred_at: Annotated[date, Form()],
    symptom_type: Annotated[str, Form()] = "",
    severity: Annotated[str, Form()] = "",
    trend: Annotated[str, Form()] = SymptomTrend.UNKNOWN.value,
    medication_event_type: Annotated[str, Form()] = MedicationEventType.TAKEN.value,
    reason: Annotated[str, Form()] = "",
):
    occurred_dt = datetime.combine(occurred_at, datetime.min.time(), tzinfo=UTC)
    now = datetime.now(UTC)
    event_type = HealthEventType.SYMPTOM if kind == "symptom" else HealthEventType.MEDICATION
    health_event = await services().health_events.record_health_event(
        patient_id=patient_id,
        checkin_id=None,
        event_type=event_type,
        occurred_at=occurred_dt,
        observed_at=now,
        source=HealthEventSource.PATIENT_REPORT,
    )
    if kind == "symptom":
        await services().health_events.record_symptom_event(
            health_event_id=health_event.id,
            symptom_type=symptom_type,
            severity=severity or None,
            onset_at=occurred_dt,
            onset_is_estimated=False,
            trend=SymptomTrend(trend),
            notes=None,
        )
    else:
        active = await services().medication_repo.get_active(patient_id)
        if active is None:
            return RedirectResponse(
                f"/patients/{patient_id}?error=no_active_medication&tab=playground", status_code=303
            )
        await services().health_events.record_medication_event(
            health_event_id=health_event.id,
            patient_medication_id=active.patient_medication_id,
            event_type=MedicationEventType(medication_event_type),
            scheduled_at=occurred_dt,
            occurred_at=occurred_dt,
            reason=reason or None,
        )
    return RedirectResponse(
        f"/patients/{patient_id}?success=health_event_recorded&tab=playground", status_code=303
    )


@app.post("/patients/{patient_id}/context/missed-checkins")
async def seed_missed_checkins(patient_id: UUID, count: Annotated[int, Form()]):
    await services().checkins.seed_missed(patient_id, count, datetime.now(UTC))
    return RedirectResponse(
        f"/patients/{patient_id}?success=checkins_seeded&tab=playground", status_code=303
    )


@app.get("/patients/{patient_id}/call")
async def patient_call(request: Request, patient_id: UUID):
    context = await services().patient_context.get_patient_context(patient_id)
    return templates.TemplateResponse(
        request,
        "call.html",
        {"context": context, "bot_base_url": Settings().bot_base_url},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8090)
