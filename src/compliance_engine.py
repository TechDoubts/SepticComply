"""
SepticComply Compliance Engine v1.0
Deterministic scheduling for 5-state septic compliance (TX, FL, CA, OH, PA).
All rules sourced from compliance_rules_v1.json with verified_date 2026-10-23.
"""
from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class TankType(Enum):
    CONVENTIONAL = "conventional"
    ATU = "atu"
    CESSPOOL = "cesspool"


class ComplianceStatus(Enum):
    COMPLIANT = "compliant"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    UNKNOWN = "unknown"


@dataclass
class Tank:
    id: str
    state: str
    county: Optional[str] = None
    municipality: Optional[str] = None
    local_board: Optional[str] = None
    tank_gallons: int = 1000
    household_size: int = 4
    tank_type: TankType = TankType.CONVENTIONAL
    last_pumped: Optional[date] = None
    installed_date: Optional[date] = None
    hauler_license: Optional[str] = None
    hauler_expiry: Optional[str] = None


@dataclass
class ScheduleResult:
    tank_id: str
    state: str
    next_due: date
    interval_years: float
    status: ComplianceStatus
    days_until_due: int
    escalation_level: int
    penalty_risk_usd_per_day: Optional[float]
    flags: list[str]
    compliance_notes: list[str]
    rule_version: str
    verified_date: str


@dataclass
class EscalationEvent:
    level: int
    days_before_due: int
    escalation_date: date
    message_template: str


@dataclass
class EscalationSchedule:
    tank_id: str
    schedule: list[EscalationEvent]


@dataclass
class InspectorReport:
    tank_id: str
    state: str
    generated_at: date
    rule_version: str
    rules_verified_date: str
    tank_specs: dict[str, Any]
    compliance: dict[str, Any]
    service_history: list[dict[str, Any]]
    hauler: dict[str, Any]
    jurisdiction: dict[str, Any]
    flags: list[str]
    notes: list[str]
    disclaimer: str


class ComplianceEngine:
    """Deterministic compliance engine for septic tank scheduling."""

    ESCALATION_DAYS = [90, 60, 30, 7]

    def __init__(self, rules_path: Optional[Path] = None):
        if rules_path is None:
            rules_path = Path(__file__).parent.parent / "config" / "compliance_rules_v1.json"
        with open(rules_path, "r") as f:
            self.rules = json.load(f)
        self.version = self.rules["engine_version"]
        self.verified_date = self.rules["verified_date"]

    def calculate_schedule(self, tank: Tank) -> ScheduleResult:
        """Calculate compliance schedule for a tank."""
        interval_years = self._calculate_interval(tank)
        next_due = self._calculate_next_due(tank, interval_years)
        days_until_due = (next_due - date.today()).days
        status = self._get_status(days_until_due)
        escalation_level = self._get_escalation_level(days_until_due)
        penalty_risk = self._get_penalty_risk(tank.state)
        flags = self._collect_flags(tank)
        notes = self._collect_compliance_notes(tank)

        return ScheduleResult(
            tank_id=tank.id,
            state=tank.state,
            next_due=next_due,
            interval_years=interval_years,
            status=status,
            days_until_due=days_until_due,
            escalation_level=escalation_level,
            penalty_risk_usd_per_day=penalty_risk,
            flags=flags,
            compliance_notes=notes,
            rule_version=self.version,
            verified_date=self.verified_date,
        )

    def get_escalation_schedule(self, tank: Tank) -> EscalationSchedule:
        """Generate escalation schedule for notifications."""
        schedule_result = self.calculate_schedule(tank)
        events = []

        for i, days_before in enumerate(self.ESCALATION_DAYS):
            escalation_date = schedule_result.next_due - timedelta(days=days_before)
            if escalation_date >= date.today():
                level = i + 1
                template = self._get_message_template(tank, schedule_result, days_before, level)
                events.append(EscalationEvent(
                    level=level,
                    days_before_due=days_before,
                    escalation_date=escalation_date,
                    message_template=template
                ))

        return EscalationSchedule(tank_id=tank.id, schedule=events)

    def generate_inspector_report(self, tank: Tank) -> InspectorReport:
        """Generate full inspector report."""
        schedule = self.calculate_schedule(tank)

        return InspectorReport(
            tank_id=tank.id,
            state=tank.state,
            generated_at=date.today(),
            rule_version=self.version,
            rules_verified_date=self.verified_date,
            tank_specs={
                "gallons": tank.tank_gallons,
                "household_size": tank.household_size,
                "type": tank.tank_type.value,
                "installed_date": tank.installed_date.isoformat() if tank.installed_date else None,
                "last_pumped": tank.last_pumped.isoformat() if tank.last_pumped else None,
            },
            compliance={
                "next_due": schedule.next_due.isoformat(),
                "interval_years": schedule.interval_years,
                "status": schedule.status.value,
                "days_until_due": schedule.days_until_due,
                "escalation_level": schedule.escalation_level,
            },
            service_history=[],
            hauler={
                "license": tank.hauler_license,
                "expiry": tank.hauler_expiry,
                "validated": tank.hauler_license is not None,
            },
            jurisdiction=self._get_jurisdiction(tank),
            flags=schedule.flags,
            notes=schedule.compliance_notes,
            disclaimer=(
                "This schedule follows published state guidelines. "
                "Local ordinances may impose stricter requirements. "
                "Verify with your local health department."
            ),
        )

    def _calculate_interval(self, tank: Tank) -> float:
        """Calculate pumping interval in years based on state rules."""
        state_rules = self.rules["states"].get(tank.state, {})
        cross_state = self.rules["cross_state_rules"]

        if tank.tank_type == TankType.ATU:
            return state_rules.get("pump_interval_years", {}).get("atu", cross_state["atu"]["primary_pump_years_range"][1])

        if tank.tank_type == TankType.CESSPOOL:
            return cross_state["default_interval_years"]

        if tank.state == "TX":
            return self._lookup_tx_interval(tank)

        return state_rules.get("pump_interval_years", {}).get("default", cross_state["default_interval_years"])

    def _lookup_tx_interval(self, tank: Tank) -> float:
        """Lookup Texas pumping interval from table."""
        table = self.rules["states"]["TX"]["pump_interval_years"]["table"]
        sizes = sorted([int(k) for k in table.keys()])
        households = sorted([int(k) for k in next(iter(table.values())).keys()])

        closest_size = min(sizes, key=lambda x: abs(x - tank.tank_gallons))
        closest_hh = min(households, key=lambda x: abs(x - tank.household_size))

        return table[str(closest_size)][str(closest_hh)]

    def _calculate_next_due(self, tank: Tank, interval_years: float) -> date:
        """Calculate next due date from last_pumped or installed_date."""
        if tank.last_pumped:
            base = tank.last_pumped
        elif tank.installed_date:
            base = tank.installed_date
        else:
            base = date.today()

        return base + timedelta(days=int(interval_years * 365.25))

    def _get_status(self, days_until_due: int) -> ComplianceStatus:
        """Determine compliance status."""
        if days_until_due < 0:
            return ComplianceStatus.OVERDUE
        elif days_until_due <= 90:
            return ComplianceStatus.DUE_SOON
        else:
            return ComplianceStatus.COMPLIANT

    def _get_escalation_level(self, days_until_due: int) -> int:
        """Get current escalation level (0=none, 1=90d, 2=60d, 3=30d, 4=7d, 5=overdue)."""
        if days_until_due < 0:
            return 5
        for i, days in enumerate(self.ESCALATION_DAYS):
            if days_until_due <= days:
                return i + 1
        return 0

    def _get_penalty_risk(self, state: str) -> Optional[float]:
        """Get penalty risk per day for a state."""
        state_rules = self.rules["states"].get(state, {})
        penalty = state_rules.get("penalty_usd_per_day")
        return float(penalty) if penalty is not None else None

    def _collect_flags(self, tank: Tank) -> list[str]:
        """Collect compliance flags for a tank."""
        flags = []
        state_rules = self.rules["states"].get(tank.state, {})
        cross_state = self.rules["cross_state_rules"]

        if state_rules.get("hauler_required") and not tank.hauler_license:
            flags.append("hauler_missing")

        if tank.tank_type == TankType.CESSPOOL:
            flags.append(cross_state["cesspools"]["flag"])

        if tank.tank_type == TankType.ATU:
            flags.append("atu_system")

        if state_rules.get("county_override") and not tank.county:
            flags.append("county_not_specified_variance_possible")

        if state_rules.get("local_override") and not tank.local_board:
            flags.append("local_board_not_specified_rules_may_differ")

        if state_rules.get("municipal_override") and not tank.municipality:
            flags.append("municipality_not_specified_smp_may_differ")

        if state_rules.get("real_estate_trigger"):
            flags.append("real_estate_inspection_flag")

        flags.extend(state_rules.get("flags", []))
        return flags

    def _collect_compliance_notes(self, tank: Tank) -> list[str]:
        """Collect compliance notes for a tank."""
        notes = []
        state_rules = self.rules["states"].get(tank.state, {})
        cross_state = self.rules["cross_state_rules"]

        notes.extend(state_rules.get("compliance_notes", []))

        if tank.tank_type == TankType.ATU:
            notes.append("ATU systems require quarterly maintenance visits (cross-state requirement)")

        notes.append(
            "This schedule follows published state guidelines. "
            "Local ordinances may impose stricter requirements. "
            "Verify with your local health department."
        )

        return notes

    def _get_jurisdiction(self, tank: Tank) -> dict[str, Any]:
        """Get jurisdiction info for inspector report."""
        state_rules = self.rules["states"].get(tank.state, {})
        return {
            "state": tank.state,
            "county": tank.county,
            "municipality": tank.municipality,
            "local_board": tank.local_board,
            "regulator": state_rules.get("regulator"),
            "override_enabled": any([
                state_rules.get("county_override"),
                state_rules.get("local_override"),
                state_rules.get("municipal_override"),
            ]),
        }

    def _get_message_template(self, tank: Tank, schedule: ScheduleResult, days_before: int, level: int) -> str:
        """Generate message template for escalation."""
        return (
            f"SepticComply {days_before}-day reminder: "
            f"Tank {tank.id} in {tank.state} is due for pumping on {schedule.next_due}. "
            f"Days until due: {schedule.days_until_due}. "
            f"Escalation level: {level}. "
            f"Contact your hauler to schedule service."
        )


def load_engine(rules_path: Optional[Path] = None) -> ComplianceEngine:
    """Factory function to load compliance engine."""
    return ComplianceEngine(rules_path)


if __name__ == "__main__":
    engine = load_engine()
    print(f"Engine v{engine.version} loaded, rules verified {engine.verified_date}")
    print(f"States supported: {list(engine.rules['states'].keys())}")