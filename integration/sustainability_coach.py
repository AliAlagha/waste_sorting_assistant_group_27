import logging
import os
import random

from .errors import IntegrationError

logger = logging.getLogger(__name__)

# every answer focuses on one of these, so scanning the same item again teaches something new
ANGLES = [
    "what happens to this item after collection and what it is turned into",
    "how to prepare it correctly before throwing it away, and the most common mistake people make",
    "its environmental impact if it ends up in the wrong bin",
    "a surprising fact about this kind of waste",
    "a reusable or lower-waste alternative to buy next time",
    "how much energy or raw material is saved when it is disposed of correctly",
]


class SustainabilityCoach:
    # AI sustainability coach (OpenAI API): explains a scan, answers questions, writes dashboard insights

    def __init__(self, api_key=None, model=None, client=None, timeout=20):
        self._api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self._model = model or os.environ.get("OPENAI_MODEL", "gpt-6-luna")
        self._client = client
        self._timeout = timeout

    def is_enabled(self):
        return self._client is not None or self._api_key != ""

    def get_model(self):
        return self._model

    def explain(self, item_name, category, bin_name, region_name):
        # a new explanation and tip for every scan
        prompt = ("A citizen in {} scanned: {}. It is {} and goes into the {}. In at most 3 short sentences, "
                  "say in one sentence why it belongs there, then focus on {}."
                  ).format(region_name, item_name, category, bin_name, random.choice(ANGLES))
        return self._answer(prompt)

    def ask(self, question, rules, region_name):
        # free question ("Where does a pizza box go?"); rules = (item, category, bin, tip) of the local rules
        question = (question or "").strip()
        if len(question) < 3:
            raise IntegrationError("please type a question, for example: Where does a pizza box go?", 400)
        facts = "\n".join("- {}: {} -> {} ({})".format(*rule) for rule in rules)
        prompt = ("Local recycling rules of {}:\n{}\n\nQuestion of a citizen: {}\n\nAnswer in at most 4 short "
                  "sentences. Use the local rules when they fit, otherwise give general German waste sorting "
                  "advice. If the question is not about waste, recycling or sustainability, politely say "
                  "you can only help with that.").format(region_name, facts, question[:300])
        return self._answer(prompt)

    def summarize(self, statistics):
        # 3 insights for the municipality dashboard
        numbers = {k: statistics.get(k) for k in ("scans", "recycling_rate", "waste_composition", "most_common_items",
                                                  "composition_by_region", "previous", "region_filter", "date_filter")}
        prompt = ("You advise a city waste department. These are the scan statistics of a waste sorting app "
                  "(date_filter = number of days, previous = the period before): {}\n\nWrite exactly 3 short "
                  "bullet points (start each with '- '): one observation, one comparison or trend, and one "
                  "concrete action the city could take. Use the numbers.").format(numbers)
        return self._answer(prompt)

    def _answer(self, prompt):
        if not self.is_enabled():
            raise IntegrationError("the AI coach is not configured (OPENAI_API_KEY is missing)", 503)
        try:
            if self._client is None:
                from openai import OpenAI
                self._client = OpenAI(api_key=self._api_key, timeout=self._timeout)
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "system", "content": "You are a friendly sustainability coach. Be concise."},
                          {"role": "user", "content": prompt}],
            )
        except Exception as error:
            logger.warning("OpenAI request failed: %s", error)
            raise IntegrationError("the AI coach is not available right now", 503)
        return {"text": response.choices[0].message.content.strip(), "source": "OpenAI " + self._model}
