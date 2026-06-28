import datetime
import os
import re
import requests
import time
import json
from pypdf import PdfReader
from prometheus_client import start_http_server, Gauge, REGISTRY, PROCESS_COLLECTOR, PLATFORM_COLLECTOR

REGISTRY.unregister(PROCESS_COLLECTOR)
REGISTRY.unregister(PLATFORM_COLLECTOR)
try:
    from prometheus_client import GC_COLLECTOR
    REGISTRY.unregister(GC_COLLECTOR)
except AttributeError:
    pass

PORT = int(os.environ.get("EXPORTER_PORT", 9163))
SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL", 86400))
CACHE_FILE = os.environ.get("EDF_CACHE_FILE", "edf_price_cache.json")
PDF_URL = os.environ.get("EDF_PDF_URL", "https://particulier.edf.fr/content/dam/2-Actifs/Documents/Offres/grille-prix-zen-week-end-plus.pdf")


WEEKDAY_MAP = {
    "monday": 0, "lundi": 0,
    "tuesday": 1, "mardi": 1,
    "wednesday": 2, "mercredi": 2,
    "thursday": 3, "jeudi": 3,
    "friday": 4, "vendredi": 4,
    "saturday": 5, "samedi": 5,
    "sunday": 6, "dimanche": 6
}

EDF_CURRENT_PRICE = Gauge('edf_current_price', 'Current active electricity price in EUR/kWh')
EDF_IS_DISCOUNT = Gauge('edf_is_discount_day', '1 if today is a discount rate day (weekend/chosen day), else 0')
EDF_SCRAPE_ERROR = Gauge('edf_scrape_error', '1 if the last PDF scrape failed and fell back to cache, else 0')

env_day = os.environ.get("EDF_CHOSEN_DAY", "wednesday").lower()
chosen_weekday = WEEKDAY_MAP.get(env_day, 2)

def save_to_cache(standard, discount):
    """Saves successfully scraped rates to a local JSON file."""
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump({"standard_rate": standard, "discount_rate": discount}, f)
    except Exception as e:
        print(f"Warning: Could not write cache file: {e}")

def load_from_cache():
    """Loads the last known good rates from the local JSON file."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                data = json.load(f)
                return float(data.get("standard_rate")), float(data.get("discount_rate"))
        except Exception as e:
            print(f"Warning: Could not read cache file: {e}")
    return 0.0, 0.0

def fetch_and_evaluate_rates():
    global chosen_weekday
    standard_rate, discount_rate = load_from_cache()
    is_scrape_failed = True
    option = "Option WE"
    regex = r"\b6\s+\d{2},\d{2}\s+(\d{2},\d{2})\s+(\d{2},\d{2})"
    if PDF_URL.endswith("grille-prix-zen-week-end.pdf"):
        option = "Option Week-End"
        chosen_weekday = 6
    if PDF_URL.endswith("Grille-prix-zen-fixe.pdf"):
        option = "Option Base"
        regex = r"\b6\s+\d{2},\d{2}\s+(\d{2},\d{2})"

    try:
        response = requests.get(PDF_URL, timeout=10)

        with open("edf_grid.pdf", "wb") as f:
            f.write(response.content)

        reader = PdfReader("edf_grid.pdf")
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text()


        lines = full_text.split("\n")

        for i, line in enumerate(lines):
            if option in line:
                for sub_line in lines[i+15:i+30]:
                    match = re.search(regex, sub_line)
                    if match:
                        standard_rate = float(match.group(1).replace(",", ".")) / 100
                        discount_rate = float(match.group(2).replace(",", ".")) / 100 if option != "Option Base" else standard_rate
                        save_to_cache(standard_rate, discount_rate)
                        is_scrape_failed = False
                        break
                if standard_rate:
                    break
    except Exception:
        is_scrape_failed = True

    EDF_SCRAPE_ERROR.set(1 if is_scrape_failed else 0) 

    today = datetime.datetime.now()
    current_weekday = today.weekday()

    is_discount_day = current_weekday in [5, 6, chosen_weekday]
    active_rate = discount_rate if is_discount_day else standard_rate
    
    EDF_CURRENT_PRICE.set(active_rate)
    EDF_IS_DISCOUNT.set(1 if is_discount_day else 0)

if __name__ == '__main__':
    start_http_server(PORT, addr='0.0.0.0')
    print(f"EDF Pricing Exporter started on port {PORT}")
    print(f"Configured Chosen Weekday: {env_day.upper()}")
    print(f"Configured PDF URL: {PDF_URL}")

    while True:
        fetch_and_evaluate_rates()
        time.sleep(SCRAPE_INTERVAL)
