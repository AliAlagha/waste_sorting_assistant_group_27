import base64
import io

import matplotlib

matplotlib.use("Agg")   # no window, the charts are only saved as pictures
import matplotlib.pyplot as plt  # noqa: E402

# same colours as the web UI: green = recycling, brown = compost, grey = landfill
PRIMARY = "#1E7F4F"
COLORS = {"Recyclable": PRIMARY, "Compostable": "#9A6A3A", "Landfill": "#C4CADA"}
TEXT = "#4B5675"
TITLE = "#071437"
GRID = "#F1F1F4"

plt.rcParams.update({
    "font.size": 9, "text.color": TEXT, "axes.labelcolor": TEXT, "xtick.color": TEXT, "ytick.color": TEXT,
    "axes.edgecolor": GRID, "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlecolor": TITLE,
    "axes.titlelocation": "left", "axes.titlepad": 12, "axes.spines.top": False, "axes.spines.right": False,
    "axes.spines.left": False, "axes.grid": True, "grid.color": GRID, "axes.axisbelow": True,
    "xtick.major.size": 0, "ytick.major.size": 0, "legend.frameon": False,
})


class ChartBuilder:
    # draws the dashboard charts with matplotlib and returns them as base64 PNG

    def composition_chart(self, totals):
        fig, ax = plt.subplots(figsize=(6, 3.5))
        if totals:
            labels = list(totals)
            _, _, percents = ax.pie(totals.values(), labels=labels, autopct="%1.0f%%", startangle=90,
                                    pctdistance=0.79, colors=[COLORS.get(label, GRID) for label in labels],
                                    wedgeprops={"width": 0.42, "edgecolor": "white", "linewidth": 2})
            for text, label in zip(percents, labels):
                text.set_color(TITLE if label == "Landfill" else "white")   # readable on dark and light slices
                text.set_fontweight("bold")
        else:
            self._no_data(ax)
        ax.set_title("Waste composition")
        return self._to_base64(fig)

    def recycling_trend_chart(self, rates_by_week):
        fig, ax = plt.subplots(figsize=(6, 3.5))
        if rates_by_week:
            weeks = [week[5:] for week in rates_by_week]          # "2026-11-15" -> "11-15"
            ax.plot(weeks, list(rates_by_week.values()), marker="o", markersize=4, linewidth=2, color=PRIMARY)
            ax.fill_between(weeks, list(rates_by_week.values()), color=PRIMARY, alpha=0.06)
            ax.set_ylim(0, 100)
            ax.set_ylabel("% recyclable")
            ax.grid(axis="x", visible=False)
        else:
            self._no_data(ax)
        ax.set_title("Recycling rate per week")
        return self._to_base64(fig)

    def common_items_chart(self, items):
        fig, ax = plt.subplots(figsize=(6, 3.5))
        if items:
            names = list(items)[::-1]
            ax.barh(names, [items[n] for n in names], color=PRIMARY, height=0.55)
            ax.set_xlabel("scans")
            ax.grid(axis="y", visible=False)
        else:
            self._no_data(ax)
        ax.set_title("Most common items")
        return self._to_base64(fig)

    def region_chart(self, composition_by_region):
        fig, ax = plt.subplots(figsize=(6, 3.5))
        regions = list(composition_by_region)
        bottom = [0] * len(regions)
        for category in COLORS:
            values = [composition_by_region[r].get(category, 0) for r in regions]
            ax.bar(regions, values, bottom=bottom, label=category, color=COLORS[category], width=0.5)
            bottom = [b + v for b, v in zip(bottom, values)]
        if regions:
            ax.legend(fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=3)
            ax.grid(axis="x", visible=False)
        else:
            self._no_data(ax)
        ax.set_title("Scans per region")
        return self._to_base64(fig)

    def _no_data(self, ax):
        ax.text(0.5, 0.5, "no scans", ha="center", va="center")
        ax.axis("off")

    def _to_base64(self, fig):
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=110, bbox_inches="tight", pad_inches=0.15)
        plt.close(fig)
        return base64.b64encode(buffer.getvalue()).decode("ascii")
