from datetime import date, timedelta

from .errors import RecommendationError

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
NO_ADDRESS = "depends on your address"
NOT_AT_ADDRESS = "not collected at this address"

# How often each bin is emptied in Dortmund (EDG, normal household).
# The weekday is different for every street, so it is not known without an address.
DORTMUND_RHYTHM = {
    "Grey bin": 2,     # Restabfall
    "Yellow bin": 2,   # Wertstoffe
    "Brown bin": 2,    # Bioabfall
    "Blue bin": 4,     # Altpapier
}


class CollectionSchedule:

    def __init__(self, region_name, address=""):
        self._region_name = region_name
        self._address = address
        self._pickup_days = {}
        self._rhythm_weeks = {}
        self._known_dates = {}
        self._calendar_dates = {}   # real dates from the EDG calendar (with holiday changes)
        self._containers = {}       # bin -> list of (EDG title, usual date, weeks)

    def load_default_days(self):
        # without an address we only know the rhythm, not the day
        self._address = ""
        self._pickup_days = {}
        self._known_dates = {}
        self._calendar_dates = {}
        self._containers = {}
        for bin_name in DORTMUND_RHYTHM:
            self._pickup_days[bin_name] = NO_ADDRESS
            self._rhythm_weeks[bin_name] = DORTMUND_RHYTHM[bin_name]

    def load_address(self, street, house_number, calendar=None):
        # real dates of one address from the EDG calendar
        if calendar is None:
            from .edg_calendar import EdgCalendar
            calendar = EdgCalendar()
        events = calendar.get_events(street, house_number)
        if len(events) == 0:
            raise RecommendationError("the EDG calendar has no dates for " + street + " " + str(house_number))
        self.load_default_days()
        # show the address the way EDG knows it, so the user sees which building was found
        edg_address = getattr(calendar, "last_address", "")
        self._address = (edg_address or street + " " + str(house_number)) + ", Dortmund"
        # one address can have several bins of the same kind (e.g. a 60 l and a 1100 l grey bin),
        # each with its own day and rhythm, so we group the dates by container (= EDG title)
        containers = {}
        for day, bin_name, title in events:
            self._calendar_dates.setdefault(bin_name, []).append(day)
            containers.setdefault(bin_name, {}).setdefault(title, []).append(day)
        for bin_name in DORTMUND_RHYTHM:
            if bin_name not in containers:
                # EDG does not empty this bin here (e.g. offices without a brown bin)
                self._pickup_days[bin_name] = NOT_AT_ADDRESS
                self._rhythm_weeks[bin_name] = 0
        for bin_name in containers:
            plans = []
            for title in containers[bin_name]:
                plans.append(self._container_plan(title, containers[bin_name][title]))
            # main plan = the container that is emptied most often
            plans.sort(key=lambda plan: (plan[2], plan[1]))
            self._containers[bin_name] = plans
            self.set_plan(bin_name, plans[0][1], plans[0][2])
            weekdays = sorted(set(plan[1].weekday() for plan in plans))
            self._pickup_days[bin_name] = " and ".join(DAYS[d] for d in weekdays)

    def _container_plan(self, title, dates):
        # (title, one usual date, rhythm in weeks) of one container
        from .edg_calendar import rhythm_weeks
        weeks = rhythm_weeks(title)
        if weeks == 0 and len(dates) > 1:
            weeks = max(1, round((dates[1] - dates[0]).days / 7))
        # a holiday can move one date, so we take the weekday that comes most often
        weekdays = [d.weekday() for d in dates]
        usual_day = max(set(weekdays), key=weekdays.count)
        known_date = [d for d in dates if d.weekday() == usual_day][0]
        return title, known_date, max(weeks, 1)

    def get_containers(self, bin_name):
        # e.g. ["Restabfall 60 l: Friday, every week", ...] when there is more than one bin of a kind
        lines = []
        for title, known_date, weeks in self._containers.get(bin_name, []):
            size = " ".join(title.split()[:3])
            lines.append(size + ": " + DAYS[known_date.weekday()] + ", " + self._weeks_text(weeks))
        return lines

    # region
    def get_region_name(self):
        return self._region_name

    def set_region_name(self, region_name):
        self._region_name = region_name

    # address
    def get_address(self):
        return self._address

    def has_address(self):
        return self._address != ""

    # pickup days
    def get_pickup_days(self):
        return self._pickup_days

    def set_pickup_day(self, bin_name, day):
        if day not in DAYS:
            raise RecommendationError(day + " is not a day")
        self._pickup_days[bin_name] = day

    # rhythm
    def get_rhythm_weeks(self, bin_name):
        return self._rhythm_weeks.get(bin_name, 0)

    def set_plan(self, bin_name, known_date, weeks):
        # one known date + the rhythm are enough to calculate the other dates
        if not isinstance(known_date, date):
            raise RecommendationError("known_date must be a date")
        if weeks < 1:
            raise RecommendationError("rhythm must be at least 1 week")
        self._known_dates[bin_name] = known_date
        self._rhythm_weeks[bin_name] = weeks
        self.set_pickup_day(bin_name, DAYS[known_date.weekday()])

    # functions
    def get_pickup_day(self, bin_name):
        if bin_name in self._pickup_days:
            return self._pickup_days[bin_name]
        # containers and collection points are not picked up from home
        return "no pickup, bring it there yourself"

    def get_next_pickup(self, bin_name, today=None):
        if today is None:
            today = date.today()
        # 1) the real EDG dates (they already include holiday changes)
        for day in self._calendar_dates.get(bin_name, []):
            if day >= today:
                return day
        # 2) calculated from one known date and the rhythm (of every container of this bin)
        plans = self._containers.get(bin_name, [])
        if len(plans) == 0 and bin_name in self._known_dates:
            plans = [("", self._known_dates[bin_name], self._rhythm_weeks[bin_name])]
        found = []
        for title, known_date, weeks in plans:
            step = timedelta(weeks=weeks)
            next_date = known_date
            while next_date < today:
                next_date += step
            while next_date - step >= today:
                next_date -= step
            found.append(next_date)
        if len(found) == 0:
            return None
        return min(found)

    def get_rhythm_text(self, bin_name):
        return self._weeks_text(self.get_rhythm_weeks(bin_name))

    def _weeks_text(self, weeks):
        if weeks == 0:
            return ""
        if weeks == 1:
            return "every week"
        return "every " + str(weeks) + " weeks"

    def is_pickup_today(self, bin_name):
        return self.get_next_pickup(bin_name) == date.today()

    def show(self):
        if self.has_address():
            print("Collection plan for " + self._address + ":")
        else:
            print("Collection plan for " + self._region_name + " (no address given):")
        for bin_name in self._pickup_days:
            line = "  " + bin_name + ": " + self._pickup_days[bin_name]
            if self.get_rhythm_text(bin_name) != "":
                line += ", " + self.get_rhythm_text(bin_name)
            next_date = self.get_next_pickup(bin_name)
            if next_date is not None:
                line += ", next " + str(next_date) + " (" + DAYS[next_date.weekday()] + ")"
            print(line)
            if len(self._containers.get(bin_name, [])) > 1:
                for container in self.get_containers(bin_name):
                    print("      " + container)
