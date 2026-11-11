# AI-Powered Waste Sorting and Recycling Assistant

Capstone project, Python course 2026, FH Dortmund. **Group 27**, Topic 2.

A web app where citizens photograph a waste item and learn how to dispose of it. An AI model classifies the item
(recyclable, compostable or landfill), the app shows the local rules and collection days of Dortmund (EDG),
an OpenAI sustainability coach explains the decision, and the municipality gets a dashboard of what is thrown away.
The image model is [`watersplash/waste-classification`](https://huggingface.co/watersplash/waste-classification)
(a Vision Transformer fine-tuned on the Kaggle Garbage Classification dataset).

## Presentation and video

- Screencast (7 min): _add link here_
- Final presentation: _add link / file here_

## Team

| Member | Student ID | Subsystem |
|---|---|---|
| Amirhossein Owji | 7227410 | AI waste classification |
| Mahshid Jafari | 7227434 | Recycling recommendations |
| Ali Alagha | 7226045 | History and statistics, User interface and integration |

## How to start

Requirements: Docker and an OpenAI API key.

```bash
cp .env.example .env              # put your OPENAI_API_KEY into .env
docker compose up --build         # app + MySQL database
```

Open http://localhost:5050. Demo accounts (also a switch in the header):

| Role | Username | Password |
|---|---|---|
| Citizen | `citizen` | `citizen123` |
| Municipality | `city` | `city12345` |
| Admin | `admin` | `admin12345` |

Run the unit tests (32 tests, one file per subsystem):

```bash
docker compose exec app python -m pytest
```

## System design

Class diagram of each subsystem (main classes, their attributes and methods).

### AI waste classification (Amirhossein Owji)

Validates the uploaded photo, classifies it with the image model and returns the item, category, confidence, top 3 predictions and status (`ok`, `uncertain`, `error`).

```mermaid
classDiagram
    class ClassificationService {
        +validator : ImageValidator
        +classifier : WasteClassifier
        +mapper : CategoryMapper
        +confidence_threshold : float
        +top_k : int
        +__init__(validator: ImageValidator, classifier: WasteClassifier, mapper: CategoryMapper) None
        +from_settings()$ ClassificationService
        +classify(data: bytes) ClassificationResult
        +classify_file(path: str or Path) ClassificationResult
    }
    class ImageValidator {
        +max_bytes : int
        +min_resolution : int
        +allowed_formats : Iterable~str~
        +__init__() None
        +validate(data: bytes) Image
    }
    class WasteClassifier {
        +backend : ImageClassifierBackend
        +__init__(backend: ImageClassifierBackend) None
        +model_version() str
        +predict(image: Image) List~Prediction~
    }
    class ClassificationResult {
        +status : str
        +item : str
        +category : str
        +confidence : float
        +top_predictions : List~Prediction~
        +message : str
        +error_code : str
        +model_version : str
        +processing_ms : float
        +timestamp : str
        +error(code: str, message: str)$ ClassificationResult
        +is_error() bool
        +to_dict() Dict~str, Any~
    }
    ClassificationService "1" *-- "1" ImageValidator : validator
    ClassificationService "1" *-- "1" WasteClassifier : classifier
    ClassificationService ..> ClassificationResult : creates
```

### Recycling recommendations (Mahshid Jafari)

Turns the classification into the right bin and preparation tip (EDG rules) and reads the real collection days of the user's address from the EDG website.

```mermaid
classDiagram
    class RecommendationService {
        #region_name : str
        #rules : list
        #schedule : CollectionSchedule
        #address_schedules : dict
        #calendar : EdgCalendar
        #history : list
        +__init__()
        +load_rules()
        +set_address(street: str, house_number: str)
        +get_schedule_for(street: str, house_number: str) CollectionSchedule
        +add_rule(rule: RecyclingRule)
        +remove_rule(item_name: str)
        +get_rule_count() int
        +find_rules_by_category(category: str) list
        +recommend(result: ClassificationResult) Recommendation
        +get_region_name() str
        +get_rules() list
        +get_schedule() CollectionSchedule
        +get_history() list
        +set_region_name(region_name: str)
    }
    class RecyclingRule {
        #item_name : str
        #category : str
        #bin_name : str
        #tip : str
        +__init__(item_name: str, category: str, bin_name: str)
        +is_recyclable() bool
        +has_tip() bool
        +get_item_name() str
        +get_category() str
        +get_bin_name() str
        +get_tip() str
        +set_item_name(item_name: str)
        +set_category(category: str)
        +set_bin_name(bin_name: str)
        +set_tip(tip: str)
    }
    class CollectionSchedule {
        #region_name : str
        #address : str
        #pickup_days : dict
        #rhythm_weeks : dict
        #known_dates : dict
        #calendar_dates : dict
        #containers : dict
        +__init__(region_name: str)
        +load_default_days()
        +load_address(street: str, house_number: str)
        +get_containers(bin_name: str) list
        +has_address() bool
        +set_pickup_day(bin_name: str, day: str)
        +get_rhythm_weeks(bin_name: str) int
        +set_plan(bin_name: str, known_date: date, weeks: int)
        +get_pickup_day(bin_name: str) str
        +get_next_pickup(bin_name: str) date
        +get_rhythm_text(bin_name: str) str
        +is_pickup_today(bin_name: str) bool
        +get_region_name() str
        +get_address() str
    }
    class Recommendation {
        #rule : RecyclingRule
        #region_name : str
        #pickup_day : str
        #rhythm : str
        #next_pickup : date
        #created_at : datetime
        +__init__(rule: RecyclingRule, region_name: str)
        +get_category() str
        +get_bin_name() str
        +to_dict() dict
        +get_rule() RecyclingRule
        +get_region_name() str
        +get_pickup_day() str
        +get_rhythm() str
        +get_next_pickup() date
        +get_created_at() datetime
        +set_rule(rule: RecyclingRule)
        +set_region_name(region_name: str)
        +set_pickup_day(pickup_day: str)
    }
    RecommendationService "1" *-- "0..*" RecyclingRule : rules
    RecommendationService "1" *-- "1..*" CollectionSchedule : schedules
    RecommendationService "1" o-- "0..*" Recommendation : history
    Recommendation "0..*" --> "1" RecyclingRule : rule
```

### History and statistics (Ali Alagha)

Saves every scan in MySQL (no personal data) and calculates the dashboard statistics and charts with pandas and matplotlib (filters by region and date, CSV export).

```mermaid
classDiagram
    class Dashboard {
        #repository : ScanRepository
        #service : StatisticsService
        #charts : ChartBuilder
        #region_filter : str
        #date_filter : int
        +__init__(repository: ScanRepository)
        +get_regions() list
        +filter_data() DataFrame
        +get_statistics() dict
        +get_previous_period() dict
        +show_charts() dict
        +get_recent_scans() list
        +export_csv() str
        +get_region_filter() str
        +get_date_filter() int
        +set_region_filter(region_filter: str)
        +set_date_filter(days: int)
    }
    class StatisticsService {
        #records : list
        +__init__()
        +load_records(records: list)
        +get_dataframe() DataFrame
        +get_totals(df: DataFrame) dict
        +get_recycle_rate(df: DataFrame) float
        +get_most_common_items(df: DataFrame) dict
        +get_recycle_rate_by_week(df: DataFrame) dict
        +get_composition_by_region(df: DataFrame) dict
        +get_summary(df: DataFrame) dict
        +get_records() list
    }
    class ScanRepository {
        #database : Database
        +__init__(database: Database)
        +save(record: ScanRecord) ScanRecord
        +find() list
        +get_regions() list
        +count() int
        +anonymize_user(user_id: int)
    }
    class ScanRecord {
        #scan_id : int
        #region_name : str
        #category : str
        #item_name : str
        #scan_date : datetime
        #bin_name : str
        #confidence : float
        #status : str
        #user_id : int
        +__init__(scan_id: int, region_name: str, category: str, item_name: str)
        +is_from_today() bool
        +to_dict() dict
        +get_scan_id() int
        +get_region_name() str
        +get_category() str
        +get_item_name() str
        +get_bin_name() str
        +get_confidence() float
        +get_status() str
        +get_user_id() int
        +set_scan_id(scan_id: int)
        +set_region_name(region_name: str)
        +set_category(category: str)
    }
    Dashboard "0..*" --> "1" ScanRepository : repository
    Dashboard "1" *-- "1" StatisticsService : service
    StatisticsService "1" o-- "0..*" ScanRecord : records
    ScanRepository ..> ScanRecord : saves / loads
```

### User interface and integration (Ali Alagha)

Flask web UI and REST API with roles (citizen, municipality, admin). The gateway sends every scan through the other subsystems and the OpenAI coach; accounts and sessions are handled by the account service.

```mermaid
classDiagram
    class ApiGateway {
        #database : Database
        #scans : ScanRepository
        #addresses : AddressDirectory
        #accounts : AccountService
        #classification : ClassificationService
        #recommendations : RecommendationService
        #coach : SustainabilityCoach
        #monitor : SystemMonitor
        +__init__()
        +setup()
        +set_calendar(calendar: EdgCalendar)
        +get_model_version() str
        +scan(token: str, image_bytes: bytes) dict
        +my_history(token: str) dict
        +my_schedule(token: str) dict
        +get_rules() list
        +ask_coach(token: str, question: str) dict
        +get_dashboard(token: str) Dashboard
        +dashboard(token: str) dict
        +dashboard_insights(token: str) dict
        +system_stats(token: str) dict
        +health() dict
    }
    class AccountService {
        #accounts : AccountRepository
        #scans : ScanRepository
        #addresses : AddressDirectory
        #sessions : dict
        +__init__(accounts: AccountRepository, scans: ScanRepository, addresses: AddressDirectory)
        +register(username: str, password: str, role: str, region_name: str) Account
        +ensure_account(username: str, password: str, role: str, region_name: str) Account
        +login(username: str, password: str) str
        +logout(token: str)
        +get_account(token: str) Account
        +require_admin(token: str)
        +update_profile(token: str, region_name: str) Account
        +change_password(token: str, old_password: str, new_password: str)
        +delete_account(token: str)
        +list_users(token: str) list
        +create_user(token: str, username: str, password: str, role: str, region_name: str) Account
        +change_role(token: str, user_id: int, role: str) Account
        +delete_user(token: str, user_id: int)
    }
    class Account {
        +ROLES : list$
        #user_id : int
        #username : str
        #password_hash : str
        #role : str
        #region_name : str
        #street : str
        #house_number : str
        #created_at : datetime
        +__init__(username: str, password: str, role: str, region_name: str)
        +set_password(password: str)
        +set_address(street: str, house_number: str)
        +check_password(password: str) bool
        +is_admin() bool
        +is_municipality() bool
        +has_address() bool
        +to_dict() dict
        +get_user_id() int
        +get_username() str
        +get_password_hash() str
        +get_role() str
        +get_region_name() str
        +get_street() str
    }
    class Session {
        +DEFAULT_MINUTES : int$
        #account : Account
        #minutes : int
        #token : str
        #expires_at : datetime
        +__init__(account: Account)
        +start()
        +is_expired() bool
        +extend()
        +end()
        +get_token() str
        +get_account() Account
        +set_expires_at(expires_at: datetime)
    }
    ApiGateway "1" *-- "1" AccountService : accounts
    AccountService "1" *-- "0..*" Session : sessions
    AccountService ..> Account : creates / loads
    Session "0..*" --> "1" Account : account
```
