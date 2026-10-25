"""
SepticComply API v1.0
FastAPI REST API for septic tank compliance management.
"""
from __future__ import annotations
import os
from datetime import date
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from src.compliance_engine import (
    ComplianceEngine,
    InspectorReport,
    EscalationSchedule,
    ScheduleResult,
    Tank,
    TankType,
    load_engine,
)
from src.database import (
    TankRecord,
    add_service_record,
    clear_all_data,
    create_tank,
    delete_tank,
    get_dashboard_stats,
    get_service_history,
    get_tank,
    init_db,
    list_tanks,
    update_tank,
)


app = FastAPI(
    title="SepticComply API",
    version="1.0.0",
    description="Septic tank compliance scheduling and management API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine: ComplianceEngine = load_engine()


class TankCreateRequest(BaseModel):
    state: str = Field(..., description="State code (TX, FL, CA, OH, PA)")
    county: Optional[str] = None
    municipality: Optional[str] = None
    local_board: Optional[str] = None
    tank_gallons: int = Field(..., ge=500, le=5000)
    household_size: int = Field(..., ge=1, le=20)
    tank_type: str = Field(..., description="conventional, atu, or cesspool")
    last_pumped: Optional[str] = None
    installed_date: Optional[str] = None
    hauler_license: Optional[str] = None
    hauler_expiry: Optional[str] = None

    @field_validator("state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        valid_states = {"TX", "FL", "CA", "OH", "PA"}
        if v.upper() not in valid_states:
            raise ValueError(f"State must be one of: {', '.join(valid_states)}")
        return v.upper()

    @field_validator("tank_type")
    @classmethod
    def validate_tank_type(cls, v: str) -> str:
        valid_types = {"conventional", "atu", "cesspool"}
        if v.lower() not in valid_types:
            raise ValueError(f"Tank type must be one of: {', '.join(valid_types)}")
        return v.lower()

    @field_validator("last_pumped", "installed_date", "hauler_expiry")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")


class TankUpdateRequest(BaseModel):
    county: Optional[str] = None
    municipality: Optional[str] = None
    local_board: Optional[str] = None
    tank_gallons: Optional[int] = Field(None, ge=500, le=5000)
    household_size: Optional[int] = Field(None, ge=1, le=20)
    tank_type: Optional[str] = None
    last_pumped: Optional[str] = None
    installed_date: Optional[str] = None
    hauler_license: Optional[str] = None
    hauler_expiry: Optional[str] = None

    @field_validator("tank_type")
    @classmethod
    def validate_tank_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        valid_types = {"conventional", "atu", "cesspool"}
        if v.lower() not in valid_types:
            raise ValueError(f"Tank type must be one of: {', '.join(valid_types)}")
        return v.lower()

    @field_validator("last_pumped", "installed_date", "hauler_expiry")
    @classmethod
    def validate_date_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")


class ServiceRecordRequest(BaseModel):
    service_date: str
    hauler_license: Optional[str] = None
    gallons_pumped: Optional[int] = None
    notes: Optional[str] = None

    @field_validator("service_date")
    @classmethod
    def validate_date_format(cls, v: str) -> str:
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")


class TankResponse(BaseModel):
    id: str
    state: str
    county: Optional[str]
    municipality: Optional[str]
    local_board: Optional[str]
    tank_gallons: int
    household_size: int
    tank_type: str
    last_pumped: Optional[str]
    installed_date: Optional[str]
    hauler_license: Optional[str]
    hauler_expiry: Optional[str]
    created_at: str
    updated_at: str


class PaginatedTanksResponse(BaseModel):
    tanks: list[TankResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class ScheduleResponse(BaseModel):
    tank_id: str
    state: str
    next_due: str
    interval_years: float
    status: str
    days_until_due: int
    escalation_level: int
    penalty_risk_usd_per_day: Optional[float]
    flags: list[str]
    compliance_notes: list[str]
    rule_version: str
    verified_date: str


class EscalationEventResponse(BaseModel):
    level: int
    days_before_due: int
    escalation_date: str
    message_template: str


class EscalationScheduleResponse(BaseModel):
    tank_id: str
    schedule: list[EscalationEventResponse]


class InspectorReportResponse(BaseModel):
    tank_id: str
    state: str
    generated_at: str
    rule_version: str
    rules_verified_date: str
    tank_specs: dict
    compliance: dict
    service_history: list[dict]
    hauler: dict
    jurisdiction: dict
    flags: list[str]
    notes: list[str]
    disclaimer: str


class HealthResponse(BaseModel):
    status: str
    version: str
    engine_version: str
    engine_verified_date: str
    tanks_tracked: int


class ErrorResponse(BaseModel):
    detail: str


def validate_hauler(state: str, hauler_license: Optional[str], hauler_expiry: Optional[str]) -> None:
    """Validate hauler license per state rules."""
    state_rules = engine.rules["states"].get(state, {})
    if state_rules.get("hauler_required", True):
        if not hauler_license:
            raise HTTPException(status_code=400, detail="hauler_license is required for this state")
        if hauler_expiry:
            try:
                expiry_date = date.fromisoformat(hauler_expiry)
                if expiry_date < date.today():
                    raise HTTPException(status_code=400, detail="Hauler license has expired")
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid hauler expiry date format")


def tank_record_to_engine(tank: TankRecord) -> Tank:
    """Convert database record to engine Tank object."""
    return Tank(
        id=tank.id,
        state=tank.state,
        county=tank.county,
        municipality=tank.municipality,
        local_board=tank.local_board,
        tank_gallons=tank.tank_gallons,
        household_size=tank.household_size,
        tank_type=TankType(tank.tank_type),
        last_pumped=date.fromisoformat(tank.last_pumped) if tank.last_pumped else None,
        installed_date=date.fromisoformat(tank.installed_date) if tank.installed_date else None,
        hauler_license=tank.hauler_license,
        hauler_expiry=tank.hauler_expiry,
    )


def schedule_result_to_response(schedule: ScheduleResult) -> ScheduleResponse:
    """Convert engine ScheduleResult to API response."""
    return ScheduleResponse(
        tank_id=schedule.tank_id,
        state=schedule.state,
        next_due=schedule.next_due.isoformat(),
        interval_years=schedule.interval_years,
        status=schedule.status.value,
        days_until_due=schedule.days_until_due,
        escalation_level=schedule.escalation_level,
        penalty_risk_usd_per_day=schedule.penalty_risk_usd_per_day,
        flags=schedule.flags,
        compliance_notes=schedule.compliance_notes,
        rule_version=schedule.rule_version,
        verified_date=schedule.verified_date,
    )


def escalation_schedule_to_response(escalation: EscalationSchedule) -> EscalationScheduleResponse:
    """Convert engine EscalationSchedule to API response."""
    return EscalationScheduleResponse(
        tank_id=escalation.tank_id,
        schedule=[
            EscalationEventResponse(
                level=e.level,
                days_before_due=e.days_before_due,
                escalation_date=e.escalation_date.isoformat(),
                message_template=e.message_template,
            )
            for e in escalation.schedule
        ],
    )


def inspector_report_to_response(report: InspectorReport) -> InspectorReportResponse:
    """Convert engine InspectorReport to API response."""
    return InspectorReportResponse(
        tank_id=report.tank_id,
        state=report.state,
        generated_at=report.generated_at.isoformat(),
        rule_version=report.rule_version,
        rules_verified_date=report.rules_verified_date,
        tank_specs=report.tank_specs,
        compliance=report.compliance,
        service_history=report.service_history,
        hauler=report.hauler,
        jurisdiction=report.jurisdiction,
        flags=report.flags,
        notes=report.notes,
        disclaimer=report.disclaimer,
    )


@app.on_event("startup")
async def startup():
    init_db()


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Health check endpoint."""
    stats = get_dashboard_stats()
    return HealthResponse(
        status="healthy",
        version="1.0.0",
        engine_version=engine.version,
        engine_verified_date=engine.verified_date,
        tanks_tracked=stats["total_tanks"],
    )


@app.post("/tanks", response_model=TankResponse, status_code=201, tags=["Tanks"])
async def create_tank_endpoint(request: TankCreateRequest):
    """Create a new septic tank."""
    validate_hauler(request.state, request.hauler_license, request.hauler_expiry)

    tank = create_tank(
        state=request.state,
        county=request.county,
        municipality=request.municipality,
        local_board=request.local_board,
        tank_gallons=request.tank_gallons,
        household_size=request.household_size,
        tank_type=request.tank_type,
        last_pumped=request.last_pumped,
        installed_date=request.installed_date,
        hauler_license=request.hauler_license,
        hauler_expiry=request.hauler_expiry,
    )
    return TankResponse(**tank.__dict__)


@app.get("/tanks", response_model=PaginatedTanksResponse, tags=["Tanks"])
async def list_tanks_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all tanks with pagination."""
    result = list_tanks(page=page, page_size=page_size)
    return PaginatedTanksResponse(
        tanks=[TankResponse(**t) for t in result["tanks"]],
        total=result["total"],
        page=result["page"],
        page_size=result["page_size"],
        total_pages=result["total_pages"],
    )


@app.get("/tanks/{tank_id}", response_model=TankResponse, tags=["Tanks"])
async def get_tank_endpoint(tank_id: str):
    """Get a single tank by ID."""
    tank = get_tank(tank_id)
    if not tank:
        raise HTTPException(status_code=404, detail="Tank not found")
    return TankResponse(**tank.__dict__)


@app.patch("/tanks/{tank_id}", response_model=TankResponse, tags=["Tanks"])
async def update_tank_endpoint(tank_id: str, request: TankUpdateRequest):
    """Update tank fields."""
    tank = get_tank(tank_id)
    if not tank:
        raise HTTPException(status_code=404, detail="Tank not found")

    updates = request.model_dump(exclude_unset=True)
    if "hauler_license" in updates or "hauler_expiry" in updates:
        validate_hauler(tank.state, updates.get("hauler_license"), updates.get("hauler_expiry"))

    updated = update_tank(tank_id, **updates)
    if not updated:
        raise HTTPException(status_code=404, detail="Tank not found")
    return TankResponse(**updated.__dict__)


@app.delete("/tanks/{tank_id}", status_code=204, tags=["Tanks"])
async def delete_tank_endpoint(tank_id: str):
    """Delete a tank and its service history."""
    deleted = delete_tank(tank_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Tank not found")


@app.get("/tanks/{tank_id}/schedule", response_model=ScheduleResponse, tags=["Compliance"])
async def get_schedule(tank_id: str):
    """Get compliance schedule for a tank."""
    tank_record = get_tank(tank_id)
    if not tank_record:
        raise HTTPException(status_code=404, detail="Tank not found")

    engine_tank = tank_record_to_engine(tank_record)
    schedule = engine.calculate_schedule(engine_tank)
    return schedule_result_to_response(schedule)


@app.get("/tanks/{tank_id}/escalation-schedule", response_model=EscalationScheduleResponse, tags=["Compliance"])
async def get_escalation_schedule(tank_id: str):
    """Get escalation schedule for notifications."""
    tank_record = get_tank(tank_id)
    if not tank_record:
        raise HTTPException(status_code=404, detail="Tank not found")

    engine_tank = tank_record_to_engine(tank_record)
    escalation = engine.get_escalation_schedule(engine_tank)
    return escalation_schedule_to_response(escalation)


@app.get("/tanks/{tank_id}/inspector-report", response_model=InspectorReportResponse, tags=["Compliance"])
async def get_inspector_report(tank_id: str):
    """Generate inspector report for a tank."""
    tank_record = get_tank(tank_id)
    if not tank_record:
        raise HTTPException(status_code=404, detail="Tank not found")

    engine_tank = tank_record_to_engine(tank_record)
    report = engine.generate_inspector_report(engine_tank)
    return inspector_report_to_response(report)


@app.post("/tanks/{tank_id}/service", response_model=dict, status_code=201, tags=["Service History"])
async def add_service(tank_id: str, request: ServiceRecordRequest):
    """Add a service history record."""
    tank = get_tank(tank_id)
    if not tank:
        raise HTTPException(status_code=404, detail="Tank not found")

    record = add_service_record(
        tank_id=tank_id,
        service_date=request.service_date,
        hauler_license=request.hauler_license,
        gallons_pumped=request.gallons_pumped,
        notes=request.notes,
    )
    return record


@app.get("/tanks/{tank_id}/service", response_model=list[dict], tags=["Service History"])
async def get_service_history_endpoint(tank_id: str):
    """Get service history for a tank."""
    tank = get_tank(tank_id)
    if not tank:
        raise HTTPException(status_code=404, detail="Tank not found")
    return get_service_history(tank_id)


@app.get("/dashboard/stats", response_model=dict, tags=["Dashboard"])
async def dashboard_stats():
    """Get dashboard statistics."""
    return get_dashboard_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))