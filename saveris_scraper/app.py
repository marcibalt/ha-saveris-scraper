import os
import re
import json
import time
import threading
import subprocess
from typing import Optional, Dict, List

from flask import Flask, jsonify# type: ignore
from pathlib import Path
from selenium import webdriver # type: ignore
from selenium.webdriver.common.by import By# type: ignore
from selenium.webdriver.chrome.service import Service as ChromeService# type: ignore
from selenium.webdriver.support.ui import WebDriverWait# type: ignore
from selenium.webdriver.support import expected_conditions as EC# type: ignore
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException# type: ignore






LOGIN_URL = "https://www.saveris.net/users/login"
MEASURING_POINTS_URL = "https://www.saveris.net/MeasuringPts"

# Provided by Dockerfile
CHROME_BIN = os.getenv("CHROME_BIN", "/usr/bin/chromium-browser")
CHROMEDRIVER_BIN = os.getenv("CHROMEDRIVER_BIN", "/usr/bin/chromedriver")

OPTIONS_PATH = Path("/data/options.json")

def log_versions():
    try:
        print("Chromium:", subprocess.check_output([CHROME_BIN, "--version"], text=True).strip())
    except Exception as e:
        print("Chromium version check failed:", e)
    try:
        print("ChromeDriver:", subprocess.check_output([CHROMEDRIVER_BIN, "--version"], text=True).strip())
    except Exception as e:
        print("ChromeDriver version check failed:", e)

log_versions()

def load_options():
    """
    Home Assistant add-on options live in /data/options.json
    """
    if OPTIONS_PATH.exists():
        try:
            data = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}

_opts = load_options()
EMAIL = str(_opts.get("email", "") or "").strip()
PASSWORD = str(_opts.get("password", "") or "").strip()
SCAN_INTERVAL = int(_opts.get("scan_interval_seconds", 300) or 300)


app = Flask(__name__)

_latest = {
    "status": "init",
    "count": 0,
    "measuring_points": []
}
_latest_lock = threading.Lock()


# ----------------- helpers -----------------

def _extract_float(s: str) -> Optional[float]:
    if not s:
        return None
    m = re.match(r"\s*([+-]?\d+(?:\.\d+)?)", s.strip())
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def parse_measurements_cell(cell_text: str) -> Dict[str, Optional[float]]:
    lines = [ln.strip() for ln in (cell_text or "").splitlines() if ln.strip()]
    out = {
        "temperature_c": None,
        "humidity_pct": None,
        "dew_point_c": None,
        "absolute_humidity_gm3": None,
    }

    for ln in lines:
        l = ln.lower()
        v = _extract_float(ln)
        if v is None:
            continue
        if "°c td" in l:
            out["dew_point_c"] = v
        elif "%rh" in l:
            out["humidity_pct"] = v
        elif "g/m³" in l or "g/m3" in l:
            out["absolute_humidity_gm3"] = v
        elif "°c" in l:
            out["temperature_c"] = v

    return out


# ----------------- selenium -----------------

def open_browser(headless: bool = True) -> webdriver.Chrome:
    opts = webdriver.ChromeOptions()
    opts.binary_location = CHROME_BIN

    if headless:
        opts.add_argument("--headless=new")
        opts.add_argument("--disable-gpu")

    # Container stability flags
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-default-apps")
    opts.add_argument("--disable-sync")
    opts.add_argument("--metrics-recording-only")
    opts.add_argument("--mute-audio")
    opts.add_argument("--window-size=1400,1000")

    # IMPORTANT: unique user-data-dir per run to avoid deadlocks
    profile_dir = f"/tmp/chrome-profile-{int(time.time()*1000)}"
    opts.add_argument(f"--user-data-dir={profile_dir}")

    # Tell chromedriver to be a bit more patient starting chrome
    service = ChromeService(
        executable_path=CHROMEDRIVER_BIN,
        service_args=["--verbose", "--log-path=/tmp/chromedriver.log"]
    )

    # Start driver (optional; webdriver.Chrome can start it, but explicit start helps debugging)
    service.start()

    try:
        return webdriver.Chrome(service=service, options=opts)
    except Exception:
        try:
            service.stop()
        except Exception:
            pass
        raise





def find_first(driver: webdriver.Chrome, selectors):
    for by, sel in selectors:
        try:
            return driver.find_element(by, sel)
        except NoSuchElementException:
            continue
    return None


def login(driver: webdriver.Chrome, email: str, password: str, timeout: int = 30) -> None:
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, timeout)

    wait.until(lambda d: find_first(d, [
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[name='email']"),
        (By.CSS_SELECTOR, "input[name='username']"),
        (By.CSS_SELECTOR, "input[type='text']"),
    ]) is not None)

    email_input = find_first(driver, [
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[name='email']"),
        (By.CSS_SELECTOR, "input[name='username']"),
        (By.CSS_SELECTOR, "input[type='text']"),
    ])
    pwd_input = find_first(driver, [
        (By.CSS_SELECTOR, "input[type='password']"),
        (By.XPATH, "//input[@type='password']"),
    ])

    if not email_input or not pwd_input:
        raise RuntimeError("Could not locate email/password inputs")

    email_input.clear()
    email_input.send_keys(email)
    pwd_input.clear()
    pwd_input.send_keys(password)

    submit = find_first(driver, [
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "input[type='submit']"),
        (By.XPATH, "//button[contains(., 'Login') or contains(., 'Log in') or contains(., 'Sign in')]"),
    ])

    if submit:
        submit.click()
    else:
        pwd_input.send_keys("\n")

    try:
        wait.until(lambda d: d.current_url != LOGIN_URL)
    except TimeoutException:
        pass


def parse_measuring_points(driver: webdriver.Chrome) -> List[Dict]:
    results: List[Dict] = []

    tbody = driver.find_element(By.CSS_SELECTOR, "#measuring-points tbody")
    trs = tbody.find_elements(By.XPATH, "./tr")

    for tr in trs:
        if "row-details" in (tr.get_attribute("class") or ""):
            continue

        tds = tr.find_elements(By.TAG_NAME, "td")
        if len(tds) < 7:
            continue

        measuring_point = (tds[2].text or "").strip()

        try:
            group = (tds[3].find_element(By.TAG_NAME, "a").text or "").strip()
        except NoSuchElementException:
            group = (tds[3].text or "").strip() or None

        cell_text = (tds[4].get_attribute("innerText") or tds[4].text or "").strip()
        parsed = parse_measurements_cell(cell_text)

        last_meas = (tds[5].text or "").strip() or None
        internal_id = (tds[6].text or "").strip() or None

        results.append({
            "measuring_point": measuring_point,
            "group": group,
            "temperature_c": parsed["temperature_c"],
            "humidity_pct": parsed["humidity_pct"],
            "dew_point_c": parsed["dew_point_c"],
            "absolute_humidity_gm3": parsed["absolute_humidity_gm3"],
            "last_measurement": last_meas,
            "internal_id": internal_id,
        })

    return results


# ----------------- scrape loop -----------------

def scrape_once() -> Dict:
    if not EMAIL or not PASSWORD:
        return {
            "status": "error",
            "error": "Missing EMAIL or PASSWORD add-on options",
            "count": 0,
            "measuring_points": [],
        }

    driver = None
    try:
        driver = open_browser(headless=True)
        login(driver, EMAIL, PASSWORD)

        driver.get(MEASURING_POINTS_URL)
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#measuring-points tbody"))
        )
        time.sleep(1.0)

        rows = parse_measuring_points(driver)
        return {
            "status": "ok",
            "count": len(rows),
            "measuring_points": rows,
        }

    except (RuntimeError, WebDriverException, TimeoutException) as e:
        return {
            "status": "error",
            "error": str(e),
            "count": 0,
            "measuring_points": [],
        }

    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass


def background_loop():
    global _latest
    while True:
        data = scrape_once()
        with _latest_lock:
            _latest = data
        time.sleep(max(30, SCAN_INTERVAL))


# ----------------- http api -----------------

@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/data")
def data():
    with _latest_lock:
        return jsonify(_latest)
    
@app.get("/diag")
def diag():
    from pathlib import Path
    import json

    p = Path("/data/options.json")
    exists = p.exists()
    raw = ""
    keys = []
    email_present = False
    password_present = False

    if exists:
        try:
            raw = p.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict) and isinstance(data.get("options"), dict):
                data = data["options"]
            if isinstance(data, dict):
                keys = sorted(list(data.keys()))
                email_present = bool(str(data.get("email", "")).strip())
                password_present = bool(str(data.get("password", "")).strip())
        except Exception:
            pass

    return jsonify({
        "options_file_exists": exists,
        "options_keys": keys,
        "email_present": email_present,
        "password_present": password_present
    })

@app.get("/chromedriver_log")
def chromedriver_log():
    p = Path("/tmp/chromedriver.log")
    if not p.exists():
        return jsonify({"exists": False})
    # return last 200 lines max
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()[-200:]
    return jsonify({"exists": True, "tail": lines})



# ----------------- main -----------------

if __name__ == "__main__":
    t = threading.Thread(target=background_loop, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=8088)

