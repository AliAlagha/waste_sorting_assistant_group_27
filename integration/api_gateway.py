import logging
import time
from datetime import date

from api.app import HTTP_STATUS
from history_statistics.dashboard import Dashboard
from history_statistics.errors import StatisticsError
from history_statistics.scan_record import ScanRecord
from history_statistics.scan_repository import ScanRepository
from history_statistics.statistics_service import StatisticsService
from recommendations.edg_calendar import EdgCalendar
from recommendations.errors import RecommendationError
from recommendations.recommendation_service import RecommendationService
from waste_classification import (CategoryMapper, ClassificationService, ImageValidator, ModelLoader, Settings,
                                  WasteClassifier)

from .account_repository import AccountRepository
from .account_service import AccountService
from .address_directory import AddressDirectory
from .classified_item import ClassifiedItem
from .database import Database
from .errors import IntegrationError
from .sustainability_coach import SustainabilityCoach
from .system_monitor import SystemMonitor

logger = logging.getLogger(__name__)


class ApiGateway:
    # single entry point of the app: routes every request to the subsystems
    # (accounts and sessions are handled by AccountService, addresses by AddressDirectory)

    def __init__(self, database=None, classification=None, recommendations=None, coach=None):
        self._database = database or Database()
        self._scans = ScanRepository(self._database)
        self._addresses = AddressDirectory()
        self._accounts = AccountService(AccountRepository(self._database), self._scans, self._addresses)
        self._classification = classification
        self._recommendations = recommendations or RecommendationService()
        self._coach = coach or SustainabilityCoach()
        self._monitor = SystemMonitor(self._database)

    def setup(self):
        self._database.create_tables()
        if self._classification is None:
            # the trained ViT model from Hugging Face (config/settings.json -> model_path), loaded once
            settings = Settings.load()
            validator = ImageValidator(settings.max_file_size_mb, settings.min_resolution, settings.allowed_formats)
            mapper = CategoryMapper.from_json(settings.resolve(settings.class_mapping_file), settings.default_category)
            backend = ModelLoader(settings.model_path).load()
            self._classification = ClassificationService(validator, WasteClassifier(backend), mapper,
                                                         settings.confidence_threshold, settings.top_k)
        if len(self._recommendations.get_rules()) == 0:
            self._recommendations.load_rules()
            self.set_calendar(EdgCalendar(timeout=15), lambda: EdgCalendar(timeout=15))

    def set_calendar(self, calendar, new_calendar=None):
        # the EDG website (tests use a fake one); new_calendar() gives a fresh EDG session for the address lists
        self._recommendations.set_calendar(calendar)
        self._addresses.set_calendar(calendar, new_calendar or (lambda: calendar))

    # accessors
    def get_accounts(self):
        return self._accounts

    def get_addresses(self):
        return self._addresses

    def get_model_version(self):
        return self._classification.classifier.model_version

    # one scan goes through the 3 other subsystems: classification -> recommendation -> history
    def scan(self, token, image_bytes):
        account = self._accounts.get_account(token)
        started = time.perf_counter()
        warnings = []

        # 1) AI classification (never raises, errors come back as a result)
        result = self._classification.classify(image_bytes)
        if result.is_error:
            raise IntegrationError(result.message, HTTP_STATUS.get(result.error_code, 500))
        item = ClassifiedItem.from_result(result, self._classification.confidence_threshold)

        # 2) local recommendation; if it fails the user still gets the classification (partial result)
        recommendation = None
        try:
            recommendation = self._recommendations.recommend(item, account.get_street(), account.get_house_number())
        except Exception as error:
            logger.warning("recommendation failed: %s", error)
            warnings.append("recommendation service is not available")
        category = recommendation.get_category() if recommendation else result.category.capitalize()
        bin_name = recommendation.get_bin_name() if recommendation else ""

        # 3) AI sustainability coach (OpenAI); if it fails the rest of the result is still shown
        coach = None
        try:
            coach = self._coach.explain(item.get_item_name(), category, bin_name or "right bin",
                                        account.get_region_name())
        except IntegrationError as error:
            warnings.append(str(error))

        # 4) history: save the scan without personal data
        record = ScanRecord(None, account.get_region_name(), category, item.get_item_name(), None, bin_name,
                            result.confidence, result.status, account.get_user_id())
        try:
            self._scans.save(record)
        except StatisticsError as error:
            logger.warning("history failed: %s", error)
            warnings.append("scan could not be saved in the history")

        return {
            "classification": result.to_dict(),
            "item_name": item.get_item_name(),
            "certain": item.is_certain(),
            "recommendation": recommendation.to_dict() if recommendation else None,
            "coach": coach,
            "scan_id": record.get_scan_id(),
            "warnings": warnings,
            "processing_ms": round((time.perf_counter() - started) * 1000, 1),
        }

    # ---------- citizen pages ----------
    def my_history(self, token, limit=50):
        # FR "show list of past scans" + a short summary calculated with pandas
        account = self._accounts.get_account(token)
        service = StatisticsService()
        service.load_records(self._scans.find(user_id=account.get_user_id()))
        df = service.get_dataframe()
        return {"scans": int(len(df)), "recycling_rate": service.get_recycle_rate(df),
                "waste_composition": service.get_totals(df),
                "history": [record.to_dict() for record in service.get_records()[:limit]]}

    def my_schedule(self, token):
        # collection plan of the user's address (real EDG dates) or the Dortmund rhythm without an address
        account = self._accounts.get_account(token)
        if account.has_address():
            try:
                schedule = self._recommendations.get_schedule_for(account.get_street(), account.get_house_number())
            except RecommendationError as error:
                raise IntegrationError(str(error), 503)
        else:
            schedule = self._recommendations.get_schedule()
        today = date.today()
        bins = []
        for bin_name in schedule.get_pickup_days():
            next_pickup = schedule.get_next_pickup(bin_name)
            bins.append({
                "bin_name": bin_name,
                "pickup_day": schedule.get_pickup_day(bin_name),
                "rhythm": schedule.get_rhythm_text(bin_name),
                "next_pickup": str(next_pickup) if next_pickup else "",
                "days_until": (next_pickup - today).days if next_pickup else None,
                "accepts": [rule.get_item_name() for rule in self._recommendations.get_rules().values()
                            if rule.get_bin_name() == bin_name],
            })
        bins.sort(key=lambda b: (b["days_until"] is None, b["days_until"] or 0))
        return {"address": schedule.get_address(), "has_address": schedule.has_address(),
                "region_name": account.get_region_name(), "bins": bins}

    # ---------- sorting guide and coach questions ----------
    def get_rules(self):
        rules = []
        for rule in self._recommendations.get_rules().values():
            rules.append({"item_name": rule.get_item_name(), "category": rule.get_category(),
                          "bin_name": rule.get_bin_name(), "tip": rule.get_tip()})
        return sorted(rules, key=lambda r: (r["bin_name"], r["item_name"]))

    def ask_coach(self, token, question):
        account = self._accounts.get_account(token)
        rules = [(r["item_name"], r["category"], r["bin_name"], r["tip"]) for r in self.get_rules()]
        return self._coach.ask(question, rules, account.get_region_name())

    # ---------- municipality pages ----------
    def get_dashboard(self, token, region_name="All", days=30):
        account = self._accounts.get_account(token)
        if not account.is_municipality():
            raise IntegrationError("only municipality users can see the dashboard", 403)
        dashboard = Dashboard(self._scans)
        dashboard.set_region_filter(region_name)
        try:
            dashboard.set_date_filter(days)
        except StatisticsError as error:
            raise IntegrationError(str(error), 400)
        return dashboard

    def dashboard(self, token, region_name="All", days=30):
        return self.get_dashboard(token, region_name, days).get_statistics()

    def dashboard_insights(self, token, region_name="All", days=30):
        return self._coach.summarize(self.dashboard(token, region_name, days))

    # ---------- admin page and monitoring ----------
    def system_stats(self, token, hours=24):
        self._accounts.require_admin(token)
        stats = self._monitor.get_stats(hours)
        stats["health"] = self.health()
        stats["users"] = self._accounts.get_user_count()
        stats["total_scans"] = self._scans.count()
        stats["storage"] = self._database.describe()
        return stats

    def health(self):
        return {
            "status": "up",
            "database": self._database.is_available(),
            "classifier": self.get_model_version() if self._classification else None,
            "openai_coach": self._coach.is_enabled(),
            "recycling_rules": len(self._recommendations.get_rules()),
        }

    def log_request(self, method, endpoint, status_code, duration_ms):
        try:
            self._database.log_request(method, endpoint, status_code, duration_ms)
        except Exception as error:
            logger.warning("request could not be logged: %s", error)
