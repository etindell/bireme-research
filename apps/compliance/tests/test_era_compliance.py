from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.compliance.models import (
    ComplianceSettings,
    ComplianceObligation,
    ComplianceTask,
    Fund,
    FundPrincipal,
    InvestorJurisdiction,
)
from apps.compliance.services.blue_sky import generate_blue_sky_task
from apps.compliance.services.task_generation import generate_tasks
from apps.organizations.models import Organization, OrganizationMembership

User = get_user_model()


def _make_org(slug="test-org"):
    return Organization.objects.create(name="Test Org", slug=slug)


def _make_user(email="user@test.com", password="testpass123"):
    return User.objects.create_user(email=email, password=password)


def _make_fund(org, name="Fund I"):
    return Fund.objects.create(
        organization=org,
        name=name,
        entity_type=Fund.EntityType.LP,
        entity_jurisdiction="US-DE",
    )


def _make_jurisdiction(org, fund, code="US-NY", name="New York", first_sale_date=None):
    return InvestorJurisdiction.objects.create(
        organization=org,
        fund=fund,
        jurisdiction_code=code,
        jurisdiction_name=name,
        first_sale_date=first_sale_date,
    )


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestComplianceSettingsERAFields(TestCase):
    def test_compliance_settings_era_fields(self):
        org = _make_org()
        cs = ComplianceSettings.objects.create(
            organization=org,
            registration_type=ComplianceSettings.RegistrationType.ERA_VENTURE_CAPITAL,
            domicile_state="US-CA",
            entity_jurisdiction="US-DE",
            firm_crd_number="12345",
            monthly_close_due_day=15,
        )
        cs.refresh_from_db()
        self.assertEqual(cs.registration_type, "ERA_VENTURE_CAPITAL")
        self.assertEqual(cs.domicile_state, "US-CA")
        self.assertEqual(cs.entity_jurisdiction, "US-DE")
        self.assertEqual(cs.firm_crd_number, "12345")
        self.assertEqual(cs.monthly_close_due_day, 15)


class TestFundCreate(TestCase):
    def test_fund_create(self):
        org = _make_org()
        fund = Fund.objects.create(
            organization=org,
            name="Test Fund II",
            entity_type=Fund.EntityType.LLC,
            entity_jurisdiction="US-CA",
            sec_file_number="801-12345",
            inception_date=date(2024, 1, 15),
        )
        fund.refresh_from_db()
        self.assertEqual(fund.name, "Test Fund II")
        self.assertEqual(fund.entity_type, "LLC")
        self.assertEqual(fund.entity_jurisdiction, "US-CA")
        self.assertEqual(fund.sec_file_number, "801-12345")
        self.assertEqual(fund.inception_date, date(2024, 1, 15))
        self.assertTrue(fund.is_active)


class TestFundPrincipalStr(TestCase):
    def test_fund_principal_str(self):
        org = _make_org()
        fund = _make_fund(org)
        principal = FundPrincipal.objects.create(
            organization=org,
            fund=fund,
            name="Alice Smith",
            title="Managing Partner",
        )
        self.assertEqual(str(principal), "Alice Smith (Managing Partner)")


class TestFundPrincipalAdvNr(TestCase):
    def test_fund_principal_adv_nr(self):
        org = _make_org()
        fund = _make_fund(org)
        principal = FundPrincipal.objects.create(
            organization=org,
            fund=fund,
            name="Jean Dupont",
            title="Partner",
            is_us_resident=False,
            requires_adv_nr=True,
        )
        self.assertFalse(principal.is_us_resident)
        self.assertTrue(principal.requires_adv_nr)


class TestInvestorJurisdictionUniqueTogether(TestCase):
    def test_investor_jurisdiction_unique_together(self):
        org = _make_org()
        fund = _make_fund(org)
        _make_jurisdiction(org, fund, code="US-NY", name="New York")
        with self.assertRaises(IntegrityError):
            _make_jurisdiction(org, fund, code="US-NY", name="New York Dup")


class TestComplianceTaskIsOverdueExcludesDeferred(TestCase):
    def test_compliance_task_is_overdue_excludes_deferred(self):
        org = _make_org()
        task = ComplianceTask.objects.create(
            organization=org,
            title="Deferred task",
            year=2025,
            month=1,
            due_date=date(2025, 1, 1),
            status=ComplianceTask.Status.DEFERRED,
        )
        self.assertFalse(task.is_overdue)


class TestComplianceTaskIsOverdueTrue(TestCase):
    def test_compliance_task_is_overdue_true(self):
        org = _make_org()
        task = ComplianceTask.objects.create(
            organization=org,
            title="Overdue task",
            year=2024,
            month=6,
            due_date=date(2024, 6, 1),
            status=ComplianceTask.Status.NOT_STARTED,
        )
        self.assertTrue(task.is_overdue)


class TestComplianceTaskDelegationFields(TestCase):
    def test_compliance_task_delegation_fields(self):
        org = _make_org()
        task = ComplianceTask.objects.create(
            organization=org,
            title="Delegated task",
            year=2026,
            month=3,
            due_date=date(2026, 3, 31),
            delegated_to=ComplianceTask.DelegatedTo.COMPLIANCE_COUNSEL,
            delegated_to_name="Outside Counsel LLP",
        )
        task.refresh_from_db()
        self.assertEqual(task.delegated_to, "COMPLIANCE_COUNSEL")
        self.assertEqual(task.delegated_to_name, "Outside Counsel LLP")


class TestComplianceTaskCostFields(TestCase):
    def test_compliance_task_cost_fields(self):
        org = _make_org()
        task = ComplianceTask.objects.create(
            organization=org,
            title="Costly task",
            year=2026,
            month=4,
            due_date=date(2026, 4, 30),
            estimated_cost=Decimal("1500.00"),
            actual_cost=Decimal("1250.50"),
        )
        task.refresh_from_db()
        self.assertEqual(task.estimated_cost, Decimal("1500.00"))
        self.assertEqual(task.actual_cost, Decimal("1250.50"))


# ---------------------------------------------------------------------------
# Blue sky service tests
# ---------------------------------------------------------------------------


class TestBlueSkyCANoFiling(TestCase):
    def test_blue_sky_ca_no_filing(self):
        org = _make_org()
        fund = _make_fund(org)
        ij = _make_jurisdiction(org, fund, code="US-CA", name="California",
                                first_sale_date=date(2026, 6, 1))
        result = generate_blue_sky_task(ij)
        self.assertIsNone(result)


class TestBlueSkyNYBeforeEvent(TestCase):
    def test_blue_sky_ny_before_event(self):
        org = _make_org()
        fund = _make_fund(org)
        first_sale = date(2026, 7, 15)
        ij = _make_jurisdiction(org, fund, code="US-NY", name="New York",
                                first_sale_date=first_sale)
        task = generate_blue_sky_task(ij)
        self.assertIsNotNone(task)
        self.assertEqual(task.due_date, first_sale - timedelta(days=1))
        self.assertIn("NY", task.title)
        self.assertIn("Form 99", task.title)


class TestBlueSkyCTAfterEvent(TestCase):
    def test_blue_sky_ct_after_event(self):
        org = _make_org()
        fund = _make_fund(org)
        first_sale = date(2026, 5, 10)
        ij = _make_jurisdiction(org, fund, code="US-CT", name="Connecticut",
                                first_sale_date=first_sale)
        task = generate_blue_sky_task(ij)
        self.assertIsNotNone(task)
        self.assertEqual(task.due_date, first_sale + timedelta(days=15))


class TestBlueSkyTXAfterEvent(TestCase):
    def test_blue_sky_tx_after_event(self):
        org = _make_org()
        fund = _make_fund(org)
        first_sale = date(2026, 8, 20)
        ij = _make_jurisdiction(org, fund, code="US-TX", name="Texas",
                                first_sale_date=first_sale)
        task = generate_blue_sky_task(ij)
        self.assertIsNotNone(task)
        self.assertEqual(task.due_date, first_sale + timedelta(days=15))


class TestBlueSkyABPlaceholder(TestCase):
    def test_blue_sky_ab_placeholder(self):
        org = _make_org()
        fund = _make_fund(org)
        ij = _make_jurisdiction(org, fund, code="CA-AB", name="Alberta")
        task = generate_blue_sky_task(ij)
        self.assertIsNotNone(task)
        self.assertIn("REQUIRES LEGAL REVIEW", task.title)
        # The linked obligation should be flagged as placeholder
        self.assertTrue(task.obligation.is_placeholder)


class TestBlueSkyNullFirstSale(TestCase):
    def test_blue_sky_null_first_sale(self):
        org = _make_org()
        fund = _make_fund(org)
        ij = _make_jurisdiction(org, fund, code="US-NY", name="New York",
                                first_sale_date=None)
        task = generate_blue_sky_task(ij)
        self.assertIsNotNone(task)
        # When first_sale is None, _create_task uses today as the effective due date
        self.assertEqual(task.due_date, timezone.now().date())


class TestBlueSkyGenericUSState(TestCase):
    def test_blue_sky_generic_us_state(self):
        org = _make_org()
        fund = _make_fund(org)
        ij = _make_jurisdiction(org, fund, code="US-FL", name="Florida")
        task = generate_blue_sky_task(ij)
        self.assertIsNotNone(task)
        self.assertIn("FL", task.title)
        self.assertIn("assessment", task.title.lower())


# ---------------------------------------------------------------------------
# Task generation tests
# ---------------------------------------------------------------------------


class TestGenerateAnnualTasks(TestCase):
    def test_generate_annual_tasks(self):
        org = _make_org()
        ComplianceObligation.objects.create(
            organization=org,
            title="Annual filing",
            frequency=ComplianceObligation.Frequency.ANNUAL,
            default_due_month=3,
            default_due_day=31,
            category=ComplianceObligation.Category.FORM_ADV,
            is_active=True,
        )
        created, _ = generate_tasks(org, 2026)
        self.assertEqual(created, 1)
        task = ComplianceTask.objects.get(organization=org, year=2026)
        self.assertEqual(task.due_date, date(2026, 3, 31))
        self.assertEqual(task.title, "Annual filing")


class TestGenerateEventDrivenSkipped(TestCase):
    def test_generate_event_driven_skipped(self):
        org = _make_org()
        ComplianceObligation.objects.create(
            organization=org,
            title="Event driven obligation",
            frequency=ComplianceObligation.Frequency.EVENT_DRIVEN,
            category=ComplianceObligation.Category.BLUE_SKY,
            is_active=True,
        )
        created, skipped = generate_tasks(org, 2026)
        self.assertEqual(created, 0)
        self.assertEqual(skipped, 1)
        self.assertFalse(ComplianceTask.objects.filter(organization=org).exists())


class TestGenerateDedupByYearObligation(TestCase):
    def test_generate_dedup_by_year_obligation(self):
        org = _make_org()
        ComplianceObligation.objects.create(
            organization=org,
            title="Annual dedup test",
            frequency=ComplianceObligation.Frequency.ANNUAL,
            default_due_month=6,
            default_due_day=30,
            category=ComplianceObligation.Category.OTHER,
            is_active=True,
        )
        generate_tasks(org, 2026)
        generate_tasks(org, 2026)
        count = ComplianceTask.objects.filter(organization=org, year=2026).count()
        self.assertEqual(count, 1)


class TestGenerateMonthlyTasks(TestCase):
    def test_generate_monthly_tasks(self):
        org = _make_org()
        ComplianceObligation.objects.create(
            organization=org,
            title="Monthly close",
            frequency=ComplianceObligation.Frequency.MONTHLY,
            default_due_day=10,
            category=ComplianceObligation.Category.MONTHLY_CLOSE,
            is_active=True,
        )
        created, _ = generate_tasks(org, 2026)
        self.assertEqual(created, 12)
        tasks = ComplianceTask.objects.filter(organization=org, year=2026)
        self.assertEqual(tasks.count(), 12)


class TestGenerateWithFund(TestCase):
    def test_generate_with_fund(self):
        """Obligations generate firm-level tasks (fund=None) by default."""
        org = _make_org()
        fund = _make_fund(org)
        ComplianceObligation.objects.create(
            organization=org,
            title="Annual filing for fund",
            frequency=ComplianceObligation.Frequency.ANNUAL,
            default_due_month=12,
            default_due_day=31,
            category=ComplianceObligation.Category.OTHER,
            is_active=True,
        )
        created, _ = generate_tasks(org, 2026)
        self.assertEqual(created, 1)
        task = ComplianceTask.objects.get(organization=org, year=2026)
        # Task generation creates firm-level tasks; fund FK is set by blue_sky service
        self.assertIsNone(task.fund)


# ---------------------------------------------------------------------------
# Seed command test
# ---------------------------------------------------------------------------


class TestSeedERAObligations(TestCase):
    def test_seed_era_obligations(self):
        org = _make_org(slug="seed-test-org")
        call_command("seed_era_obligations", "--org=seed-test-org")
        obligations = ComplianceObligation.objects.filter(organization=org, is_active=True)
        self.assertGreater(obligations.count(), 0)
        # Verify category diversity
        categories = set(obligations.values_list("category", flat=True))
        self.assertIn("FORM_ADV", categories)
        self.assertIn("BLUE_SKY", categories)
        self.assertIn("AML_CFT", categories)
        self.assertIn("MONTHLY_CLOSE", categories)


# ---------------------------------------------------------------------------
# View tests (basic)
# ---------------------------------------------------------------------------


class TestFundListView(TestCase):
    def test_fund_list_view(self):
        org = _make_org()
        user = _make_user()
        org.add_member(user, role="member")
        _make_fund(org, name="View Test Fund")
        self.client.force_login(user)
        session = self.client.session
        session["organization_id"] = org.pk
        session.save()
        response = self.client.get(reverse("compliance:fund_list"))
        self.assertEqual(response.status_code, 200)


class TestJurisdictionCreateTriggersBlueSkyCT(TestCase):
    def test_jurisdiction_create_triggers_blue_sky(self):
        """Creating an InvestorJurisdiction and calling generate_blue_sky_task
        (as the view does) creates a blue sky ComplianceTask."""
        org = _make_org()
        fund = _make_fund(org)
        ij = InvestorJurisdiction.objects.create(
            organization=org,
            fund=fund,
            jurisdiction_code="US-CT",
            jurisdiction_name="Connecticut",
            first_sale_date=date(2026, 6, 1),
            country="US",
        )
        task = generate_blue_sky_task(ij)
        self.assertIsNotNone(task)
        self.assertTrue(
            ComplianceTask.objects.filter(
                organization=org,
                fund=fund,
                tags="blue-sky",
            ).exists()
        )
        self.assertEqual(task.due_date, date(2026, 6, 1) + timedelta(days=15))


# ---------------------------------------------------------------------------
# Reminder fields test
# ---------------------------------------------------------------------------


class TestReminderFieldsDefaultFalse(TestCase):
    def test_reminder_fields_default_false(self):
        org = _make_org()
        task = ComplianceTask.objects.create(
            organization=org,
            title="Reminder defaults",
            year=2026,
            month=1,
            due_date=date(2026, 1, 31),
        )
        task.refresh_from_db()
        self.assertFalse(task.reminder_sent_90)
        self.assertFalse(task.reminder_sent_30)
        self.assertFalse(task.reminder_sent_7)
