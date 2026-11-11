import os
import secrets
import time
from datetime import datetime

from flask import (Flask, Response, flash, g, jsonify, redirect, render_template, request, send_from_directory,
                   session, url_for)

from history_statistics.dashboard import DATE_FILTERS
from integration.account import Account
from integration.api_gateway import ApiGateway
from integration.errors import IntegrationError

# sidebar: every page belongs to the subsystem whose requirement it implements
# (section, [(endpoint, label, icon, roles)]); a user only sees the pages of his role
ALL = ["guest", "citizen", "municipality", "admin"]
USERS = ["citizen", "municipality"]
MENU = [
    ("AI classification", [
        ("scan", "Scan an item", "camera", USERS),
    ]),
    ("Recycling recommendations", [
        ("guide", "Sorting guide", "book", ALL),
        ("bins", "Collection days", "calendar", USERS),
    ]),
    ("History and statistics", [
        ("history", "My history", "history", USERS),
        ("dashboard", "Dashboard", "chart-pie", ["municipality"]),
    ]),
    ("User interface and integration", [
        ("users", "Users and roles", "users", ["admin"]),
        ("system", "API log", "activity", ["admin"]),
        ("profile", "Account", "user", ["citizen", "municipality", "admin"]),
        ("api_docs", "API docs", "api", ALL),
        ("login", "Log in", "login", ["guest"]),
        ("register", "Register", "user-plus", ["guest"]),
    ]),
]

# main page of every role (after login and for the demo switch)
START_PAGE = {"citizen": "scan", "municipality": "dashboard", "admin": "users"}
ROLES = Account.ROLES

DEMO_ACCOUNTS = [
    # username, password, role, region, street, house number (see README)
    ("citizen", "citizen123", "citizen", "Dortmund", "Sonnenstraße", "96"),
    ("city", "city12345", "municipality", "Dortmund", "", ""),
    ("admin", "admin12345", "admin", "Dortmund", "", ""),
]


def create_app(gateway=None, seed_demo_data=None):
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(16)
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024
    app.config["PERMANENT_SESSION_LIFETIME"] = 3600   # web sessions expire after 1 hour

    if seed_demo_data is None:
        seed_demo_data = os.environ.get("SEED_DEMO_DATA", "true").lower() == "true"
    gateway = gateway or ApiGateway()
    gateway.setup()
    accounts = gateway.get_accounts()        # accounts, sessions, users and roles
    addresses = gateway.get_addresses()      # city list, EDG streets and house numbers
    if seed_demo_data:
        # only the demo accounts are created; every scan in the database comes from the real AI pipeline
        for account in DEMO_ACCOUNTS:
            accounts.ensure_account(*account)
    app.config["DEMO_MODE"] = seed_demo_data

    # ---------- helpers ----------
    def current_account():
        token = session.get("token")
        if not token:
            return None
        try:
            return accounts.get_account(token)
        except IntegrationError:
            session.pop("token", None)
            return None

    def api_token():
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            return header[7:]
        return session.get("token", "")

    def is_api():
        return request.path.startswith("/api/")

    def require_account(municipality=False, admin=False):
        # web pages: redirect to the login page (401) or show a message (403) via the error handler
        account = current_account()
        if account is None:
            raise IntegrationError("please log in first", 401)
        if municipality and not account.is_municipality():
            raise IntegrationError("this page is only for municipality users", 403)
        if admin and not account.is_admin():
            raise IntegrationError("this page is only for administrators", 403)
        return account

    @app.context_processor
    def add_globals():
        account = current_account()
        role = account.get_role() if account else "guest"
        menu = []
        for section, pages in MENU:
            items = [{"endpoint": e, "label": label, "icon": icon} for e, label, icon, roles in pages if role in roles]
            if items:
                menu.append({"title": section, "items": items})
        return {"account": account, "menu": menu, "demo_mode": app.config["DEMO_MODE"],
                "model_version": gateway.get_model_version(),
                "regions": addresses.get_regions(), "old": session.pop("form_data", {}),
                "year": datetime.now().year}

    # every API request is logged (endpoint, status, time)
    @app.before_request
    def start_timer():
        g.started = time.perf_counter()

    @app.after_request
    def log_request(response):
        # static files and the browser's icon request are not API requests
        if not request.path.startswith("/static") and request.path != "/favicon.ico":
            gateway.log_request(request.method, request.path, response.status_code,
                                (time.perf_counter() - g.get("started", time.perf_counter())) * 1000)
        return response

    @app.errorhandler(IntegrationError)
    def handle_integration_error(error):
        if is_api():
            return jsonify({"error": str(error)}), error.status_code
        flash(str(error), "error")
        if request.method == "POST" and request.form:
            # the form is shown again with what the user typed (never the passwords)
            session["form_data"] = {k: v for k, v in request.form.items() if "password" not in k}
        if error.status_code == 401 and request.endpoint != "login":
            return redirect(url_for("login"))
        return redirect(request.referrer or url_for("index"))

    @app.errorhandler(404)
    def handle_not_found(error):
        if is_api():
            return jsonify({"error": "page not found"}), 404
        return render_template("message.html", title="Not found", text="This page does not exist."), 404

    @app.errorhandler(413)
    def handle_too_large(error):
        if is_api():
            return jsonify({"error": "file is too large"}), 413
        flash("The file is too large.", "error")
        return redirect(url_for("scan"))

    # ---------- web pages ----------
    @app.route("/")
    def index():
        # logged-in users go straight to their main page, guests see a short introduction
        account = current_account()
        if account is not None:
            return redirect(url_for(START_PAGE[account.get_role()]))
        return render_template("index.html")

    @app.route("/favicon.ico")
    def favicon():
        return "", 204          # the icon is inline in base.html

    @app.route("/guide")
    def guide():
        return render_template("guide.html", rules=gateway.get_rules())

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if request.method == "POST":
            form = request.form
            accounts.register(form.get("username", ""), form.get("password", ""), "citizen",
                             form.get("region_name", ""), form.get("street", ""), form.get("house_number", ""))
            flash("Account created, please log in.", "success")
            return redirect(url_for("login"))
        return render_template("register.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            session.permanent = True
            session["token"] = accounts.login(request.form.get("username", ""), request.form.get("password", ""))
            account = accounts.get_account(session["token"])
            return redirect(url_for(START_PAGE[account.get_role()]))
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        accounts.logout(session.pop("token", ""))
        flash("You are logged out.", "success")
        return redirect(url_for("index"))

    @app.route("/scan", methods=["GET", "POST"])
    def scan():
        account = current_account()
        if account is None:
            raise IntegrationError("please log in first", 401)
        if request.method == "POST":
            upload = request.files.get("image")
            if upload is None or upload.filename == "":
                raise IntegrationError("please choose a photo", 400)
            result = gateway.scan(session["token"], upload.read())
            return render_template("result.html", result=result)
        return render_template("scan.html")

    @app.route("/history")
    def history():
        require_account()
        return render_template("history.html", report=gateway.my_history(session["token"]))

    @app.route("/bins")
    def bins():
        require_account()
        return render_template("bins.html", plan=gateway.my_schedule(session["token"]))

    @app.route("/profile", methods=["GET", "POST"])
    def profile():
        require_account()
        if request.method == "POST":
            form = request.form
            accounts.update_profile(session["token"], form.get("region_name", ""), form.get("street", ""),
                                   form.get("house_number", ""))
            flash("Profile saved.", "success")
            return redirect(url_for("profile"))
        return render_template("profile.html")

    @app.route("/profile/password", methods=["POST"])
    def change_password():
        require_account()
        form = request.form
        if form.get("new_password") != form.get("repeat_password"):
            raise IntegrationError("the two new passwords are not the same", 400)
        accounts.change_password(session["token"], form.get("old_password", ""), form.get("new_password", ""))
        flash("Password changed.", "success")
        return redirect(url_for("profile"))

    @app.route("/users", methods=["GET", "POST"])
    def users():
        require_account(admin=True)
        if request.method == "POST":
            form = request.form
            account = accounts.create_user(session["token"], form.get("username", ""), form.get("password", ""),
                                          form.get("role", "citizen"), form.get("region_name", ""))
            flash("User {} created.".format(account.get_username()), "success")
            return redirect(url_for("users"))
        return render_template("users.html", users=accounts.list_users(session["token"]), roles=ROLES)

    @app.route("/users/<int:user_id>/role", methods=["POST"])
    def change_role(user_id):
        require_account(admin=True)
        account = accounts.change_role(session["token"], user_id, request.form.get("role", ""))
        flash("{} is now {}.".format(account.get_username(), account.get_role()), "success")
        return redirect(url_for("users"))

    @app.route("/users/<int:user_id>/delete", methods=["POST"])
    def delete_user(user_id):
        require_account(admin=True)
        accounts.delete_user(session["token"], user_id)
        flash("User deleted. Their scans stay only as anonymous statistics.", "success")
        return redirect(url_for("users"))

    @app.route("/system")
    def system():
        require_account(admin=True)
        return render_template("system.html", stats=gateway.system_stats(session["token"]))

    @app.route("/dashboard")
    def dashboard():
        require_account(municipality=True)
        board = gateway.get_dashboard(session["token"], request.args.get("region", "All"),
                                      request.args.get("days", 30))
        return render_template("dashboard.html", stats=board.show_charts(), regions=board.get_regions(),
                               scans=board.get_recent_scans(), date_filters=DATE_FILTERS)

    @app.route("/dashboard/export.csv")
    @app.route("/api/dashboard/export.csv")
    def export_csv():
        board = gateway.get_dashboard(api_token(), request.args.get("region", "All"), request.args.get("days", 30))
        name = "scans_{}_{}days.csv".format(board.get_region_filter(), board.get_date_filter())
        return Response(board.export_csv(), mimetype="text/csv",
                        headers={"Content-Disposition": "attachment; filename=" + name})

    @app.route("/demo/switch", methods=["POST"])
    def demo_switch():
        # presentation helper: log in as one of the demo accounts with one click
        if not app.config["DEMO_MODE"]:
            raise IntegrationError("demo accounts are switched off", 404)
        role = request.form.get("role", "")
        if role not in START_PAGE:
            raise IntegrationError("unknown role: " + role, 400)
        accounts.logout(session.pop("token", ""))
        for username, password, account_role, *rest in DEMO_ACCOUNTS:
            if account_role == role:
                accounts.ensure_account(username, password, account_role, *rest)
                session.permanent = True
                session["token"] = accounts.login(username, password)
        return redirect(url_for(START_PAGE[role]))

    @app.route("/account/delete", methods=["POST"])
    def delete_account():
        accounts.delete_account(session.get("token", ""))
        session.pop("token", None)
        flash("Your account was deleted. Your scans stay only as anonymous statistics.", "success")
        return redirect(url_for("index"))

    # ---------- REST API ----------
    @app.post("/api/auth/register")
    def api_register():
        data = request.get_json(silent=True) or {}
        role = data.get("role", "citizen")
        if role != "citizen":
            raise IntegrationError("municipality accounts are created by the administrator", 403)
        account = accounts.register(data.get("username", ""), data.get("password", ""), role,
                                   data.get("region_name", ""), data.get("street", ""),
                                   data.get("house_number", ""))
        return jsonify(account.to_dict()), 201

    @app.post("/api/auth/login")
    def api_login():
        data = request.get_json(silent=True) or {}
        token = accounts.login(data.get("username", ""), data.get("password", ""))
        return jsonify({"token": token, "expires_in": 3600})

    @app.post("/api/auth/logout")
    def api_logout():
        accounts.logout(api_token())
        return jsonify({"message": "logged out"})

    @app.post("/api/scans")
    def api_scan():
        upload = request.files.get("image")
        if upload is None:
            raise IntegrationError("send the photo as multipart/form-data in the field 'image'", 400)
        return jsonify(gateway.scan(api_token(), upload.read())), 201

    @app.get("/api/scans/history")
    def api_history():
        return jsonify(gateway.my_history(api_token())["history"])

    @app.get("/api/dashboard")
    def api_dashboard():
        return jsonify(gateway.dashboard(api_token(), request.args.get("region", "All"),
                                         request.args.get("days", 30)))

    # lists for the address form (public: also needed on the register page)
    @app.get("/api/address/regions")
    def api_regions():
        return jsonify(addresses.get_regions())

    @app.get("/api/address/streets")
    def api_streets():
        return jsonify(addresses.get_streets(request.args.get("q", ""))[:50])

    @app.get("/api/address/numbers")
    def api_numbers():
        return jsonify(addresses.get_house_numbers(request.args.get("street", "")))

    @app.get("/api/me")
    def api_me():
        return jsonify(accounts.get_account(api_token()).to_dict())

    @app.patch("/api/me")
    def api_update_me():
        data = request.get_json(silent=True) or {}
        account = accounts.update_profile(api_token(), data.get("region_name", ""), data.get("street", ""),
                                         data.get("house_number", ""))
        return jsonify(account.to_dict())

    @app.post("/api/me/password")
    def api_change_password():
        data = request.get_json(silent=True) or {}
        accounts.change_password(api_token(), data.get("old_password", ""), data.get("new_password", ""))
        return jsonify({"message": "password changed"})

    @app.get("/api/me/schedule")
    def api_schedule():
        return jsonify(gateway.my_schedule(api_token()))

    @app.get("/api/rules")
    def api_rules():
        return jsonify(gateway.get_rules())

    @app.post("/api/coach/ask")
    def api_ask():
        data = request.get_json(silent=True) or {}
        return jsonify(gateway.ask_coach(api_token(), data.get("question", "")))

    @app.get("/api/dashboard/insights")
    def api_insights():
        return jsonify(gateway.dashboard_insights(api_token(), request.args.get("region", "All"),
                                                  request.args.get("days", 30)))

    @app.get("/api/system/stats")
    def api_system_stats():
        return jsonify(gateway.system_stats(api_token(), int(request.args.get("hours", 24))))

    @app.get("/api/admin/users")
    def api_users():
        return jsonify(accounts.list_users(api_token()))

    @app.post("/api/admin/users")
    def api_create_user():
        data = request.get_json(silent=True) or {}
        account = accounts.create_user(api_token(), data.get("username", ""), data.get("password", ""),
                                      data.get("role", "citizen"), data.get("region_name", ""))
        return jsonify(account.to_dict()), 201

    @app.patch("/api/admin/users/<int:user_id>")
    def api_change_role(user_id):
        data = request.get_json(silent=True) or {}
        return jsonify(accounts.change_role(api_token(), user_id, data.get("role", "")).to_dict())

    @app.delete("/api/admin/users/<int:user_id>")
    def api_delete_user(user_id):
        accounts.delete_user(api_token(), user_id)
        return jsonify({"message": "user deleted"})

    @app.delete("/api/account")
    def api_delete_account():
        accounts.delete_account(api_token())
        return jsonify({"message": "account deleted"})

    @app.get("/api/health")
    @app.get("/health")
    def api_health():
        return jsonify(gateway.health())

    @app.get("/api/openapi.json")
    def api_openapi():
        return send_from_directory(app.static_folder, "openapi.json")

    @app.get("/api/docs")
    def api_docs():
        return render_template("api_docs.html")

    return app
