"""
Engine Unit Tests (24 tests) for SepticComply Compliance Engine
Tests per TEST_PLAN.md and traceability audit requirements.
"""
import pytest
from datetime import date, timedelta

from src.compliance_engine import (
    ComplianceEngine,
    Tank,
    TankType,
    ComplianceStatus,
    load_engine,
)


@pytest.fixture
def engine():
    """Load compliance engine for testing."""
    return load_engine()


class TestTexasRules:
    """Texas-specific rule tests."""

    def test_tx_table_lookup_1000gal_4people(self, engine):
        """TX-01: 1000 gal, 4 people = 2.0 years (from table)."""
        tank = Tank(
            id="test-tx-1",
            state="TX",
            county="Harris",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2024, 6, 15),
            hauler_license="TX-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert abs(result.interval_years - 2.0) < 0.1
        assert result.state == "TX"

    def test_tx_table_lookup_1000gal_2people(self, engine):
        """TX-01: 1000 gal, 2 people = 3.3 years (from table)."""
        tank = Tank(
            id="test-tx-2",
            state="TX",
            county="Dallas",
            tank_gallons=1000,
            household_size=2,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2024, 1, 1),
            hauler_license="TX-HAULER-002",
        )
        result = engine.calculate_schedule(tank)
        assert abs(result.interval_years - 3.3) < 0.1

    def test_tx_atu_uses_atu_schedule(self, engine):
        """TX-04: ATU uses separate ATU schedule (2.5 years)."""
        tank = Tank(
            id="test-tx-atu",
            state="TX",
            county="Travis",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.ATU,
            last_pumped=date(2024, 1, 15),
            hauler_license="TX-HAULER-ATU-001",
        )
        result = engine.calculate_schedule(tank)
        assert abs(result.interval_years - 2.5) < 0.1
        assert "atu_system" in result.flags

    def test_tx_penalty_risk_25000(self, engine):
        """TX-09: Penalty risk $25,000/day for Texas."""
        tank = Tank(
            id="test-tx-penalty",
            state="TX",
            county="Harris",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2020, 1, 1),  # Overdue
            hauler_license="TX-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert result.penalty_risk_usd_per_day == 25000.0


class TestFloridaRules:
    """Florida-specific rule tests."""

    def test_fl_default_3_years(self, engine):
        """FL-01: Default interval 3 years."""
        tank = Tank(
            id="test-fl-1",
            state="FL",
            county="Miami-Dade",
            tank_gallons=1250,
            household_size=3,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2023, 6, 15),
            hauler_license="FL-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert abs(result.interval_years - 3.0) < 0.1

    def test_flags_includes_county_variance_for_fl(self, engine):
        """FL-04: County variance flag when county NOT specified."""
        tank_with_county = Tank(
            id="test-fl-county",
            state="FL",
            county="Broward",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2024, 1, 1),
            hauler_license="FL-HAULER-001",
        )
        result_with = engine.calculate_schedule(tank_with_county)
        conditional_flags = [f for f in result_with.flags if "county_not_specified" in f.lower()]
        assert len(conditional_flags) == 0

        tank_without_county = Tank(
            id="test-fl-no-county",
            state="FL",
            county=None,
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2024, 1, 1),
            hauler_license="FL-HAULER-002",
        )
        result_without = engine.calculate_schedule(tank_without_county)
        conditional_flags_2 = [f for f in result_without.flags if "county_not_specified" in f.lower()]
        assert len(conditional_flags_2) >= 1

    def test_fl_penalty_risk_15000(self, engine):
        """FL-09: Penalty risk $15,000/day for Florida."""
        tank = Tank(
            id="test-fl-penalty",
            state="FL",
            county="Miami-Dade",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2020, 1, 1),
            hauler_license="FL-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert result.penalty_risk_usd_per_day == 15000.0


class TestCaliforniaRules:
    """California-specific rule tests."""

    def test_ca_default_3_years(self, engine):
        """CA-01: Default interval 3 years."""
        tank = Tank(
            id="test-ca-1",
            state="CA",
            county="Los Angeles",
            tank_gallons=1500,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2023, 1, 15),
            hauler_license="CA-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert abs(result.interval_years - 3.0) < 0.1
        assert "real_estate_inspection_flag" in result.flags


class TestOhioRules:
    """Ohio-specific rule tests."""

    def test_oh_default_3_years(self, engine):
        """OH-01: Default interval 3 years."""
        tank = Tank(
            id="test-oh-1",
            state="OH",
            local_board="Franklin County Board",
            tank_gallons=2000,
            household_size=5,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2023, 12, 1),
            hauler_license="OH-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert abs(result.interval_years - 3.0) < 0.1


class TestPennsylvaniaRules:
    """Pennsylvania-specific rule tests."""

    def test_pa_mandatory_3_years(self, engine):
        """PA-01: Mandatory 3-year interval."""
        tank = Tank(
            id="test-pa-1",
            state="PA",
            municipality="Washington Township",
            tank_gallons=1500,
            household_size=3,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2023, 8, 1),
            hauler_license="PA-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert abs(result.interval_years - 3.0) < 0.1
        assert "mandatory_3_year" in result.flags

    def test_flags_includes_municipal_variance_for_pa(self, engine):
        """PA-03: Municipal variance flag when municipality NOT specified."""
        tank_with_muni = Tank(
            id="test-pa-muni",
            state="PA",
            municipality="Washington Township",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2024, 1, 1),
            hauler_license="PA-HAULER-001",
        )
        result_with = engine.calculate_schedule(tank_with_muni)
        conditional_flags = [f for f in result_with.flags if "municipality_not_specified" in f.lower()]
        assert len(conditional_flags) == 0

        tank_without_muni = Tank(
            id="test-pa-no-muni",
            state="PA",
            municipality=None,
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2024, 1, 1),
            hauler_license="PA-HAULER-002",
        )
        result_without = engine.calculate_schedule(tank_without_muni)
        conditional_flags_2 = [f for f in result_without.flags if "municipality_not_specified" in f.lower()]
        assert len(conditional_flags_2) >= 1


class TestCrossStateRules:
    """Cross-state rule tests."""

    def test_next_due_from_last_pumped(self, engine):
        """CS-12: Next due from last_pumped."""
        tank = Tank(
            id="test-next-due-1",
            state="FL",
            county="Test",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2024, 1, 1),
            hauler_license="FL-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        expected_due = date(2024, 1, 1) + timedelta(days=int(3.0 * 365.25))
        assert result.next_due == expected_due

    def test_next_due_from_installed_when_no_last_pumped(self, engine):
        """CS-12: Next due from installed_date when no last_pumped."""
        tank = Tank(
            id="test-next-due-2",
            state="FL",
            county="Test",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            installed_date=date(2020, 1, 1),
            hauler_license="FL-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        expected_due = date(2020, 1, 1) + timedelta(days=int(3.0 * 365.25))
        assert result.next_due == expected_due

    def test_status_overdue_when_past_due(self, engine):
        """CS-10: Status OVERDUE when past due date."""
        tank = Tank(
            id="test-status-overdue",
            state="FL",
            county="Test",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2020, 1, 1),
            hauler_license="FL-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert result.status == ComplianceStatus.OVERDUE
        assert result.days_until_due < 0
        assert result.escalation_level == 5

    def test_status_due_soon_within_90_days(self, engine):
        """CS-10/CS-11: Status DUE_SOON within 90 days, escalation level 1."""
        # Create a tank that's due within 90 days
        # 3 years = ~1095 days interval. If last pumped ~1005 days ago, due in ~90 days.
        tank = Tank(
            id="test-status-due-soon",
            state="FL",
            county="Test",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date.today() - timedelta(days=1005),
            hauler_license="FL-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert result.status == ComplianceStatus.DUE_SOON
        assert result.days_until_due <= 90
        assert result.escalation_level == 1

    def test_status_compliant_beyond_90_days(self, engine):
        """CS-10/CS-11: Status COMPLIANT beyond 90 days, escalation level 0."""
        tank = Tank(
            id="test-status-compliant",
            state="FL",
            county="Test",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date.today() - timedelta(days=30),
            hauler_license="FL-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert result.status == ComplianceStatus.COMPLIANT
        assert result.days_until_due > 90
        assert result.escalation_level == 0

    def test_escalation_schedule_90_60_30_7(self, engine):
        """CS-06/CS-11: Escalation schedule has 90, 60, 30, 7 day events."""
        tank = Tank(
            id="test-escalation",
            state="FL",
            county="Test",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date.today() - timedelta(days=30),
            hauler_license="FL-HAULER-001",
        )
        escalation = engine.get_escalation_schedule(tank)
        days_before = [e.days_before_due for e in escalation.schedule]
        assert 90 in days_before
        assert 60 in days_before
        assert 30 in days_before
        assert 7 in days_before
        assert len(escalation.schedule) == 4

    def test_no_escalation_when_overdue(self, engine):
        """CS-06: No escalation events when already overdue."""
        tank = Tank(
            id="test-no-escalation",
            state="FL",
            county="Test",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2020, 1, 1),
            hauler_license="FL-HAULER-001",
        )
        escalation = engine.get_escalation_schedule(tank)
        assert len(escalation.schedule) == 0

    def test_flags_includes_atu_for_atu_tanks(self, engine):
        """CS-02: ATU flag for ATU tanks."""
        for state in ["TX", "FL"]:
            tank = Tank(
                id=f"test-atu-{state}",
                state=state,
                county="Test" if state == "FL" else "Harris",
                tank_gallons=1000,
                household_size=4,
                tank_type=TankType.ATU,
                last_pumped=date(2024, 1, 1),
                hauler_license=f"{state}-HAULER-ATU-001",
            )
            result = engine.calculate_schedule(tank)
            assert "atu_system" in result.flags
            atu_notes = [n for n in result.compliance_notes if "ATU" in n or "quarterly" in n.lower()]
            assert len(atu_notes) >= 1

    def test_flags_includes_cesspool_flag(self, engine):
        """CS-04: Cesspool specialist required flag."""
        tank = Tank(
            id="test-cesspool",
            state="TX",
            county="Harris",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CESSPOOL,
            last_pumped=date(2024, 1, 1),
            hauler_license="TX-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert "cesspool_specialist_required" in result.flags

    def test_compliance_notes_include_disclaimer(self, engine):
        """CS-14: Standard disclaimer in all compliance notes."""
        tank = Tank(
            id="test-disclaimer",
            state="TX",
            county="Harris",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2024, 1, 1),
            hauler_license="TX-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        disclaimer_notes = [n for n in result.compliance_notes if "Local ordinances may impose stricter requirements" in n]
        assert len(disclaimer_notes) >= 1

    def test_inspector_report_structure(self, engine):
        """CS-07: Inspector report has all required fields."""
        tank = Tank(
            id="test-report",
            state="CA",
            county="Los Angeles",
            tank_gallons=1500,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2023, 1, 15),
            installed_date=date(2018, 5, 1),
            hauler_license="CA-HAULER-001",
        )
        report = engine.generate_inspector_report(tank)
        assert report.tank_id == tank.id
        assert report.state == "CA"
        assert report.rule_version == engine.version
        assert report.rules_verified_date == engine.verified_date
        assert report.tank_specs["gallons"] == 1500
        assert report.tank_specs["household_size"] == 4
        assert report.tank_specs["type"] == "conventional"
        assert "next_due" in report.compliance
        assert "interval_years" in report.compliance
        assert report.hauler["license"] == "CA-HAULER-001"
        assert report.hauler["validated"] is True
        assert report.jurisdiction["state"] == "CA"
        assert report.jurisdiction["county"] == "Los Angeles"
        assert "Local ordinances may impose stricter requirements" in report.disclaimer
        assert "Verify with your local health department" in report.disclaimer

    def test_invalid_state_fallbacks_to_default(self, engine):
        """Engine falls back to default cross-state rules for unknown state."""
        tank = Tank(
            id="test-invalid",
            state="XX",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
        )
        # Should not raise, falls back to default 3-year interval
        result = engine.calculate_schedule(tank)
        assert result.interval_years == 3.0
        assert result.state == "XX"

    def test_version_and_verified_date_propagated(self, engine):
        """CS-13: Version and verified_date in all results."""
        tank = Tank(
            id="test-version",
            state="TX",
            county="Harris",
            tank_gallons=1000,
            household_size=4,
            tank_type=TankType.CONVENTIONAL,
            last_pumped=date(2024, 1, 1),
            hauler_license="TX-HAULER-001",
        )
        result = engine.calculate_schedule(tank)
        assert result.rule_version == engine.version
        assert result.verified_date == engine.verified_date

        escalation = engine.get_escalation_schedule(tank)
        # Escalation schedule doesn't have version/verified_date directly
        # but the tank_id should match
        assert escalation.tank_id == tank.id

        report = engine.generate_inspector_report(tank)
        assert report.rule_version == engine.version
        assert report.rules_verified_date == engine.verified_date


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])