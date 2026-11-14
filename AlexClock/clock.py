import ctypes
import glob
import json
import os
import re
import select
import struct
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request

sdl = ctypes.CDLL("libSDL2-2.0.so.0")
ttf = ctypes.CDLL("libSDL2_ttf-2.0.so.0")

SDL_INIT_VIDEO = 0x00000020
SDL_INIT_JOYSTICK = 0x00000200
SDL_INIT_GAMECONTROLLER = 0x00002000
SDL_WINDOW_FULLSCREEN_DESKTOP = 0x00001001
SDL_RENDERER_ACCELERATED = 0x00000002

SDL_QUIT = 0x100
SDL_KEYDOWN = 0x300
SDL_JOYHATMOTION = 0x602
SDL_JOYBUTTONDOWN = 0x603
SDL_JOYBUTTONUP = 0x604
SDL_CONTROLLERBUTTONDOWN = 0x651
SDL_CONTROLLERBUTTONUP = 0x652

SDL_HAT_UP = 0x01
SDL_HAT_DOWN = 0x04
SDL_HAT_LEFT = 0x08
SDL_HAT_RIGHT = 0x02

SDL_CONTROLLER_BUTTON_GUIDE = 5
SDL_CONTROLLER_BUTTON_START = 6
SDL_CONTROLLER_BUTTON_LEFTSHOULDER = 9
SDL_CONTROLLER_BUTTON_RIGHTSHOULDER = 10
SDL_CONTROLLER_BUTTON_DPAD_UP = 11
SDL_CONTROLLER_BUTTON_DPAD_DOWN = 12
SDL_CONTROLLER_BUTTON_DPAD_LEFT = 13
SDL_CONTROLLER_BUTTON_DPAD_RIGHT = 14

SDLK_ESCAPE = 27
SDLK_UP = 1073741906
SDLK_DOWN = 1073741905
SDLK_LEFT = 1073741904
SDLK_RIGHT = 1073741903

# Linux input event constants (/dev/input/event*)
EV_KEY = 0x01
EV_ABS = 0x03

KEY_ESC = 1
KEY_UP = 103
KEY_DOWN = 108
KEY_LEFT = 105
KEY_RIGHT = 106
KEY_MENU = 139
BTN_TL = 310        # L1
BTN_TR = 311        # R1
BTN_START = 315     # START
BTN_MODE = 316      # MENU / Guide
BTN_Z = 309         # MENU на некоторых ревизиях
BTN_DPAD_UP = 544
BTN_DPAD_DOWN = 545
BTN_DPAD_LEFT = 546
BTN_DPAD_RIGHT = 547

ABS_HAT0X = 16
ABS_HAT0Y = 17

MENU_EVDEV_CODES = (BTN_MODE, KEY_MENU, BTN_Z)
START_EVDEV_CODES = (BTN_START,)

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")

LANG_ORDER = ["en", "ru"]

TRANSLATIONS = {
    "ru": {
        "days": ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"],
        "bright": "ЯРКОСТЬ",
        "charge": "ЗАРЯД",
        "full": "ПОЛН.",
        "na": "Н/Д",
        "offline": "Нет сети",
        "loading_weather": "Загрузка погоды...",
        "wind": "Ветер",
        "wind_unit": "м/с",
        "humidity": "Влажность",
        "hint": "ВВЕРХ/ВНИЗ: Яркость  |  ВЛЕВО/ВПРАВО (L1/R1): Язык  |  MENU+START: Выход",
        "weather": {
            0: "Ясно",
            1: "Преимущественно ясно",
            2: "Переменная облачность",
            3: "Пасмурно",
            45: "Туман",
            48: "Изморозь",
            51: "Лёгкая морось",
            53: "Морось",
            55: "Сильная морось",
            56: "Ледяная морось",
            57: "Сильная ледяная морось",
            61: "Небольшой дождь",
            63: "Дождь",
            65: "Сильный дождь",
            66: "Ледяной дождь",
            67: "Сильный ледяной дождь",
            71: "Небольшой снег",
            73: "Снег",
            75: "Сильный снег",
            77: "Снежная крупа",
            80: "Небольшой ливень",
            81: "Ливень",
            82: "Сильный ливень",
            85: "Небольшой снегопад",
            86: "Сильный снегопад",
            95: "Гроза",
            96: "Гроза с мелким градом",
            99: "Гроза с градом",
        },
    },
    "en": {
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "bright": "BRIGHTNESS",
        "charge": "BATTERY",
        "full": "FULL",
        "na": "N/A",
        "offline": "Offline",
        "loading_weather": "Loading weather...",
        "wind": "Wind",
        "wind_unit": "m/s",
        "humidity": "Humidity",
        "hint": "UP/DOWN: Brightness  |  LEFT/RIGHT (L1/R1): Lang  |  MENU+START: Exit",
        "weather": {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Rime fog",
            51: "Light drizzle",
            53: "Drizzle",
            55: "Dense drizzle",
            56: "Freezing drizzle",
            57: "Heavy freezing drizzle",
            61: "Slight rain",
            63: "Rain",
            65: "Heavy rain",
            66: "Freezing rain",
            67: "Heavy freezing rain",
            71: "Slight snow",
            73: "Snow",
            75: "Heavy snow",
            77: "Snow grains",
            80: "Slight showers",
            81: "Showers",
            82: "Violent showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with hail",
            99: "Heavy thunderstorm",
        },
    },
}

class AppConfig:
    """Хранение настроек и кэша данных в отдельном файле config.json"""
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.lock = threading.Lock()
        self.data = {
            "lang": "en",
            "city_ru": "",
            "city_en": "",
            "lat": None,
            "lon": None,
            "temp": None,
            "wcode": None,
            "wind": None,
            "humidity": None,
            "weather_text_ru": "",
            "weather_text_en": "",
            "last_error": "",
        }
        self.load()

    def load(self):
        with self.lock:
            if os.path.exists(self.path):
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self.data.update(loaded)
                except Exception:
                    pass
            else:
                self._save_unlocked()

    def _save_unlocked(self):
        try:
            tmp_path = self.path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except Exception:
            pass

    def save(self):
        with self.lock:
            self._save_unlocked()

    def get(self, key, default=None):
        with self.lock:
            return self.data.get(key, default)

    def update(self, **kwargs):
        with self.lock:
            self.data.update(kwargs)
            self._save_unlocked()

    def toggle_lang(self):
        with self.lock:
            cur = self.data.get("lang", "en")
            idx = LANG_ORDER.index(cur) if cur in LANG_ORDER else 0
            new_lang = LANG_ORDER[(idx + 1) % len(LANG_ORDER)]
            self.data["lang"] = new_lang
            self._save_unlocked()
            return new_lang

class SDL_Color(ctypes.Structure):
    _fields_ = [("r", ctypes.c_uint8), ("g", ctypes.c_uint8),
                ("b", ctypes.c_uint8), ("a", ctypes.c_uint8)]

class SDL_Rect(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int),
                ("w", ctypes.c_int), ("h", ctypes.c_int)]

class SDL_ControllerButtonEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("timestamp", ctypes.c_uint32),
        ("which", ctypes.c_int32),
        ("button", ctypes.c_uint8),
        ("state", ctypes.c_uint8),
        ("padding1", ctypes.c_uint8),
        ("padding2", ctypes.c_uint8),
    ]

class SDL_JoyHatEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("timestamp", ctypes.c_uint32),
        ("which", ctypes.c_int32),
        ("hat", ctypes.c_uint8),
        ("value", ctypes.c_uint8),
        ("padding1", ctypes.c_uint8),
        ("padding2", ctypes.c_uint8),
    ]

sdl.SDL_CreateWindow.restype = ctypes.c_void_p
sdl.SDL_CreateRenderer.restype = ctypes.c_void_p
sdl.SDL_CreateTextureFromSurface.restype = ctypes.c_void_p
sdl.SDL_GameControllerOpen.restype = ctypes.c_void_p
sdl.SDL_JoystickOpen.restype = ctypes.c_void_p
ttf.TTF_OpenFont.restype = ctypes.c_void_p
ttf.TTF_RenderUTF8_Blended.restype = ctypes.c_void_p

class LinuxInputReader:
    """Прямое чтение кнопок консоли из /dev/input/event*"""
    def __init__(self):
        self.fds = []
        self.pressed_keys = set()
        self.hat_state = {}
        for path in sorted(glob.glob("/dev/input/event*")):
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
                self.fds.append(fd)
            except Exception:
                pass
        self.ev_struct = struct.Struct("llHHi")

    def poll(self):
        actions = []
        if not self.fds:
            return actions
        try:
            readable, _, _ = select.select(self.fds, [], [], 0)
        except Exception:
            return actions

        for fd in readable:
            while True:
                try:
                    data = os.read(fd, self.ev_struct.size)
                    if len(data) < self.ev_struct.size:
                        break
                    _, _, ev_type, code, value = self.ev_struct.unpack(data)
                    if ev_type == EV_KEY:
                        if value == 1:
                            self.pressed_keys.add(code)
                            menu_held = any(k in self.pressed_keys for k in MENU_EVDEV_CODES)
                            start_held = any(k in self.pressed_keys for k in START_EVDEV_CODES)
                            if (menu_held and start_held) or code == KEY_ESC:
                                actions.append("EXIT")
                            elif code in (BTN_DPAD_UP, KEY_UP):
                                actions.append("UP")
                            elif code in (BTN_DPAD_DOWN, KEY_DOWN):
                                actions.append("DOWN")
                            elif code in (BTN_DPAD_LEFT, KEY_LEFT, BTN_DPAD_RIGHT, KEY_RIGHT, BTN_TL, BTN_TR):
                                actions.append("LANG")
                        elif value == 0:
                            self.pressed_keys.discard(code)
                    elif ev_type == EV_ABS and code in (ABS_HAT0X, ABS_HAT0Y):
                        prev = self.hat_state.get((fd, code), 0)
                        self.hat_state[(fd, code)] = value
                        if code == ABS_HAT0Y and prev == 0:
                            if value < 0:
                                actions.append("UP")
                            elif value > 0:
                                actions.append("DOWN")
                        elif code == ABS_HAT0X and prev == 0 and value != 0:
                            actions.append("LANG")
                except BlockingIOError:
                    break
                except Exception:
                    break
        return actions

    def close(self):
        for fd in self.fds:
            try:
                os.close(fd)
            except Exception:
                pass

class WeatherLocationFetcher:
    """Определение города, температуры, скорости ветра (м/с) и влажности (%)"""
    def __init__(self, config):
        self.config = config
        self.fallback_city = self._get_fallback_tz()
        self.loading = True
        thread = threading.Thread(target=self._worker, daemon=True)
        thread.start()

    def _get_fallback_tz(self):
        tz_paths = [
            "/etc/timezone",
            "/run/muos/storage/info/config/settings/clock/timezone",
        ]
        for p in tz_paths:
            if os.path.exists(p):
                try:
                    with open(p, "r") as f:
                        tz = f.read().strip()
                    if "/" in tz:
                        return tz.split("/")[-1].replace("_", " ")
                    elif tz:
                        return tz
                except Exception:
                    pass
        if os.path.islink("/etc/localtime"):
            try:
                target = os.readlink("/etc/localtime")
                if "zoneinfo/" in target:
                    return target.split("zoneinfo/")[-1].split("/")[-1].replace("_", " ")
            except Exception:
                pass
        return ""

    def _run_cmd_timeout(self, cmd, timeout_sec=5):
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            out, err = proc.communicate(timeout=timeout_sec)
            return proc.returncode, out.decode("utf-8", errors="ignore").strip(), err.decode("utf-8", errors="ignore").strip()
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            return -1, "", "timeout"

    def _http_get_text(self, url, timeout=5):
        errors = []
        for curl_bin in ("/usr/bin/curl", "/bin/curl", "curl"):
            if curl_bin.startswith("/") and not os.path.exists(curl_bin):
                continue
            try:
                rc, text, err = self._run_cmd_timeout(
                    [
                        curl_bin, "-sL", "-k", "-4",
                        "--connect-timeout", "3", "-m", str(timeout),
                        "-A", "Mozilla/5.0 AlexClock",
                        url,
                    ],
                    timeout_sec=timeout + 2,
                )
                if rc == 0 and text:
                    return text
                errors.append(f"curl({rc}):{err[:60]}")
            except Exception as e:
                errors.append(f"curl:{e}")

        for wget_bin in ("/usr/bin/wget", "/bin/wget", "wget"):
            if wget_bin.startswith("/") and not os.path.exists(wget_bin):
                continue
            try:
                rc, text, err = self._run_cmd_timeout(
                    [wget_bin, "-q", "-O", "-", url],
                    timeout_sec=timeout + 2,
                )
                if rc == 0 and text:
                    return text
                errors.append(f"wget({rc}):{err[:60]}")
            except Exception as e:
                errors.append(f"wget:{e}")

        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 AlexClock"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                text = resp.read().decode("utf-8", errors="ignore").strip()
                if text:
                    return text
        except Exception as e:
            errors.append(f"urllib:{e}")

        raise RuntimeError("; ".join(errors[-2:]) if errors else "No response")

    def _http_get_json(self, url, timeout=5):
        text = self._http_get_text(url, timeout=timeout)
        return json.loads(text)

    def _fetch_location(self):
        lat = self.config.get("lat")
        lon = self.config.get("lon")
        city_ru = self.config.get("city_ru", "")
        city_en = self.config.get("city_en", "")
        cc = ""

        try:
            data_ru = self._http_get_json("http://ip-api.com/json/?lang=ru&fields=status,city,countryCode,lat,lon", timeout=5)
            if data_ru.get("status") == "success":
                lat = data_ru.get("lat")
                lon = data_ru.get("lon")
                cc = str(data_ru.get("countryCode", "")).strip()
                c_ru = str(data_ru.get("city", "")).strip()
                if c_ru:
                    city_ru = f"{c_ru}, {cc}" if cc else c_ru
                try:
                    data_en = self._http_get_json("http://ip-api.com/json/?lang=en&fields=status,city,countryCode", timeout=5)
                    c_en = str(data_en.get("city", "")).strip()
                    if c_en:
                        city_en = f"{c_en}, {cc}" if cc else c_en
                except Exception:
                    if not city_en:
                        city_en = city_ru
                if lat is not None and lon is not None:
                    self.config.update(lat=lat, lon=lon, city_ru=city_ru, city_en=city_en)
                    return True
        except Exception as e:
            self.config.update(last_error=f"LOC:{e}")

        return (lat is not None and lon is not None)

    def _fetch_weather(self):
        lat = self.config.get("lat")
        lon = self.config.get("lon")
        city_query = self.config.get("city_en") or self.config.get("city_ru") or self.fallback_city
        err_list = []

        # 1. Open-Meteo
        if lat is not None and lon is not None:
            for scheme in ("http", "https"):
                url = (
                    f"{scheme}://api.open-meteo.com/v1/forecast?"
                    f"latitude={lat}&longitude={lon}"
                    f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
                    f"&wind_speed_unit=ms&current_weather=true"
                )
                try:
                    data = self._http_get_json(url, timeout=5)
                    temp = None
                    wcode = None
                    wind = None
                    humidity = None

                    cur = data.get("current")
                    if isinstance(cur, dict) and cur.get("temperature_2m") is not None:
                        temp = cur.get("temperature_2m")
                        wcode = cur.get("weather_code")
                        wind = cur.get("wind_speed_10m")
                        humidity = cur.get("relative_humidity_2m")

                    if temp is None:
                        cw = data.get("current_weather")
                        if isinstance(cw, dict) and cw.get("temperature") is not None:
                            temp = cw.get("temperature")
                            wcode = cw.get("weathercode")
                            if cw.get("windspeed") is not None:
                                wind = float(cw.get("windspeed")) / 3.6

                    if temp is not None:
                        t_rounded = int(round(float(temp)))
                        w_rounded = int(round(float(wind))) if wind is not None else None
                        h_rounded = int(round(float(humidity))) if humidity is not None else None
                        self.config.update(
                            temp=t_rounded,
                            wcode=wcode,
                            wind=w_rounded,
                            humidity=h_rounded,
                            weather_text_ru="",
                            weather_text_en="",
                            last_error="",
                        )
                        return True
                except Exception as e:
                    err_list.append(f"OM({scheme}):{e}")

        # 2. MET Norway
        if lat is not None and lon is not None:
            try:
                met_url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
                data = self._http_get_json(met_url, timeout=6)
                ts = data.get("properties", {}).get("timeseries", [])
                if ts:
                    inst = ts[0].get("data", {}).get("instant", {}).get("details", {})
                    temp = inst.get("air_temperature")
                    wind = inst.get("wind_speed")
                    humidity = inst.get("relative_humidity")
                    sym = ts[0].get("data", {}).get("next_1_hours", {}).get("summary", {}).get("symbol_code", "")
                    if temp is not None:
                        t_rounded = int(round(float(temp)))
                        w_rounded = int(round(float(wind))) if wind is not None else None
                        h_rounded = int(round(float(humidity))) if humidity is not None else None
                        sym_base = sym.split("_")[0]
                        met_map = {
                            "clearsky": ("Ясно", "Clear sky"),
                            "fair": ("Преимущественно ясно", "Mainly clear"),
                            "partlycloudy": ("Переменная облачность", "Partly cloudy"),
                            "cloudy": ("Пасмурно", "Overcast"),
                            "fog": ("Туман", "Fog"),
                            "lightrain": ("Небольшой дождь", "Light rain"),
                            "rain": ("Дождь", "Rain"),
                            "heavyrain": ("Сильный дождь", "Heavy rain"),
                            "lightsnow": ("Небольшой снег", "Light snow"),
                            "snow": ("Снег", "Snow"),
                            "heavysnow": ("Сильный снег", "Heavy snow"),
                            "sleet": ("Дождь со снегом", "Sleet"),
                        }
                        desc_ru, desc_en = met_map.get(sym_base, ("", ""))
                        self.config.update(
                            temp=t_rounded,
                            wcode=None,
                            wind=w_rounded,
                            humidity=h_rounded,
                            weather_text_ru=desc_ru,
                            weather_text_en=desc_en,
                            last_error="",
                        )
                        return True
            except Exception as e:
                err_list.append(f"MET:{e}")

        # 3. wttr.in
        clean_city = city_query.split(",")[0].strip() if city_query else ""
        target = f"{lat},{lon}" if (lat is not None and lon is not None) else urllib.parse.quote(clean_city)
        if target:
            try:
                txt_ru = self._http_get_text(f"http://wttr.in/{target}?format=%t|%C|%w|%h&lang=ru", timeout=5)
                parts = [x.strip() for x in txt_ru.split("|")]
                if len(parts) >= 2 and "<html" not in txt_ru.lower() and len(txt_ru) < 110:
                    t_part, desc_ru = parts[0], parts[1]
                    m = re.search(r"([+-]?\d+)", t_part)
                    if m:
                        t_rounded = int(m.group(1))
                        w_rounded = None
                        h_rounded = None
                        if len(parts) >= 3:
                            mw = re.search(r"(\d+)", parts[2])
                            if mw:
                                w_rounded = int(round(int(mw.group(1)) / 3.6))
                        if len(parts) >= 4:
                            mh = re.search(r"(\d+)", parts[3])
                            if mh:
                                h_rounded = int(mh.group(1))
                        self.config.update(
                            temp=t_rounded,
                            wcode=None,
                            wind=w_rounded,
                            humidity=h_rounded,
                            weather_text_ru=desc_ru.capitalize(),
                            weather_text_en=desc_ru.capitalize(),
                            last_error="",
                        )
                        return True
            except Exception as e:
                err_list.append(f"WTTR:{e}")

        if err_list:
            self.config.update(last_error=" | ".join(err_list[-3:]))
        return False

    def _worker(self):
        time.sleep(0.5)
        while True:
            ok = False
            for attempt in range(3):
                if self.config.get("lat") is None or self.config.get("lon") is None:
                    self._fetch_location()
                ok = self._fetch_weather()
                if ok:
                    break
                if attempt < 2:
                    time.sleep(5)

            self.loading = False
            # И после успешного обновления, и после 3 неудачных попыток ждём 30 минут (1800 секунд)
            time.sleep(1800)

    def get_location_text(self, lang):
        tr = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
        if lang == "en":
            return self.config.get("city_en") or self.config.get("city_ru") or self.fallback_city or tr["offline"]
        return self.config.get("city_ru") or self.config.get("city_en") or self.fallback_city or tr["offline"]

    def get_weather_text(self, lang):
        tr = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
        temp = self.config.get("temp")
        wcode = self.config.get("wcode")

        if temp is not None:
            sign = "+" if temp > 0 else ""
            desc = tr["weather"].get(wcode, "")
            if not desc:
                desc = self.config.get(f"weather_text_{lang}", "")
            return f"{sign}{temp}°C, {desc}" if desc else f"{sign}{temp}°C"
        elif self.loading:
            return tr["loading_weather"]
        return ""

    def get_details_text(self, lang):
        tr = TRANSLATIONS.get(lang, TRANSLATIONS["en"])
        wind = self.config.get("wind")
        humidity = self.config.get("humidity")
        items = []
        if wind is not None:
            items.append(f"{tr['wind']}: {wind} {tr['wind_unit']}")
        if humidity is not None:
            items.append(f"{tr['humidity']}: {humidity}%")
        return "   |   ".join(items)

def draw_text(renderer, font, text, color, x, y, align="center"):
    if not text:
        return
    surf = ttf.TTF_RenderUTF8_Blended(
        ctypes.c_void_p(font), text.encode("utf-8"), color
    )
    if not surf:
        return
    tex = sdl.SDL_CreateTextureFromSurface(
        ctypes.c_void_p(renderer), ctypes.c_void_p(surf)
    )
    w, h = ctypes.c_int(), ctypes.c_int()
    sdl.SDL_QueryTexture(
        ctypes.c_void_p(tex), None, None, ctypes.byref(w), ctypes.byref(h)
    )
    if align == "right":
        draw_x = x - w.value
    elif align == "left":
        draw_x = x
    else:
        draw_x = x - w.value // 2

    rect = SDL_Rect(draw_x, y - h.value // 2, w.value, h.value)
    sdl.SDL_RenderCopy(ctypes.c_void_p(renderer), ctypes.c_void_p(tex), None, ctypes.byref(rect))
    sdl.SDL_DestroyTexture(ctypes.c_void_p(tex))
    sdl.SDL_FreeSurface(ctypes.c_void_p(surf))

def draw_clock_with_seconds(renderer, font_main, font_sec, hm_str, secs_str, c_main, c_sec, center_x, center_y):
    surf_hm = ttf.TTF_RenderUTF8_Blended(ctypes.c_void_p(font_main), hm_str.encode("utf-8"), c_main)
    surf_s = ttf.TTF_RenderUTF8_Blended(ctypes.c_void_p(font_sec), f":{secs_str}".encode("utf-8"), c_sec)

    if not (surf_hm and surf_s):
        return

    tex_hm = sdl.SDL_CreateTextureFromSurface(ctypes.c_void_p(renderer), ctypes.c_void_p(surf_hm))
    tex_s = sdl.SDL_CreateTextureFromSurface(ctypes.c_void_p(renderer), ctypes.c_void_p(surf_s))

    whm, hhm = ctypes.c_int(), ctypes.c_int()
    ws, hs = ctypes.c_int(), ctypes.c_int()

    sdl.SDL_QueryTexture(ctypes.c_void_p(tex_hm), None, None, ctypes.byref(whm), ctypes.byref(hhm))
    sdl.SDL_QueryTexture(ctypes.c_void_p(tex_s), None, None, ctypes.byref(ws), ctypes.byref(hs))

    gap = int(ws.value * 0.12)
    total_w = whm.value + gap + ws.value
    start_x = center_x - total_w // 2

    rect_hm = SDL_Rect(start_x, center_y - hhm.value // 2, whm.value, hhm.value)
    sec_y = (center_y + hhm.value // 2) - hs.value - int(hhm.value * 0.12)
    rect_s = SDL_Rect(start_x + whm.value + gap, sec_y, ws.value, hs.value)

    sdl.SDL_RenderCopy(ctypes.c_void_p(renderer), ctypes.c_void_p(tex_hm), None, ctypes.byref(rect_hm))
    sdl.SDL_RenderCopy(ctypes.c_void_p(renderer), ctypes.c_void_p(tex_s), None, ctypes.byref(rect_s))

    sdl.SDL_DestroyTexture(ctypes.c_void_p(tex_hm))
    sdl.SDL_DestroyTexture(ctypes.c_void_p(tex_s))
    sdl.SDL_FreeSurface(ctypes.c_void_p(surf_hm))
    sdl.SDL_FreeSurface(ctypes.c_void_p(surf_s))

def find_font():
    candidates = [
        b"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        b"/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
        b"/opt/muos/share/theme/MustardOS/font/default.ttf",
        b"/opt/muos/share/theme/active/font/default.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    for root, _, files in os.walk(b"/opt/muos"):
        for f in files:
            if f.endswith(b".ttf"):
                return os.path.join(root, f)
    return None

def get_battery_info():
    for cap_path in sorted(glob.glob("/sys/class/power_supply/*/capacity")):
        try:
            with open(cap_path, "r") as f:
                percent = int(f.read().strip())
            status_path = os.path.join(os.path.dirname(cap_path), "status")
            status = ""
            if os.path.exists(status_path):
                with open(status_path, "r") as f:
                    status = f.read().strip()
            return percent, status
        except Exception:
            continue
    return None, ""

class BacklightController:
    def __init__(self):
        self.percent = 50
        self.max_val = 255
        self.muos_script = None
        self.sys_file = None

        script_candidates = [
            "/opt/muos/script/device/bright.sh",
            "/opt/muos/device/current/input/combo/bright.sh",
            "/opt/muos/device/script/bright.sh",
        ]
        for sc in script_candidates:
            if os.path.exists(sc):
                self.muos_script = sc
                break

        self.cfg_paths = [
            "/run/muos/storage/info/config/settings/general/brightness",
            "/opt/muos/config/settings/general/brightness",
        ]
        for cfg in self.cfg_paths:
            if os.path.exists(cfg):
                try:
                    with open(cfg, "r") as f:
                        val = int(f.read().strip())
                    self.percent = max(5, min(100, round(val * 100 / 255)))
                    break
                except Exception:
                    pass

        if os.path.exists("/sys/class/disp/disp/attr/lcd_bl"):
            self.sys_file = "/sys/class/disp/disp/attr/lcd_bl"
            self.max_val = 255
            try:
                with open(self.sys_file, "r") as f:
                    cur = int(f.read().strip())
                self.percent = max(5, min(100, round(cur * 100 / self.max_val)))
            except Exception:
                pass
        else:
            for path in sorted(glob.glob("/sys/class/backlight/*/brightness")):
                d = os.path.dirname(path)
                max_p = os.path.join(d, "max_brightness")
                if os.path.exists(max_p):
                    try:
                        with open(max_p, "r") as f:
                            self.max_val = int(f.read().strip())
                        with open(path, "r") as f:
                            cur = int(f.read().strip())
                        self.sys_file = path
                        self.percent = max(5, min(100, round(cur * 100 / self.max_val)))
                        break
                    except Exception:
                        continue

    def change(self, delta):
        self.percent = max(5, min(100, self.percent + delta))
        raw_val = max(1, int(round(self.max_val * self.percent / 100.0)))

        if self.sys_file:
            try:
                with open(self.sys_file, "w") as f:
                    f.write(str(raw_val))
            except Exception:
                pass

        if self.muos_script:
            try:
                subprocess.Popen([self.muos_script, str(raw_val)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

        for cfg in self.cfg_paths:
            if os.path.exists(cfg):
                try:
                    with open(cfg, "w") as f:
                        f.write(str(raw_val))
                except Exception:
                    pass

def main():
    sdl.SDL_Init(SDL_INIT_VIDEO | SDL_INIT_JOYSTICK | SDL_INIT_GAMECONTROLLER)
    ttf.TTF_Init()
    sdl.SDL_ShowCursor(0)

    controllers = []
    joysticks = []
    for i in range(sdl.SDL_NumJoysticks()):
        if sdl.SDL_IsGameController(i):
            ctrl = sdl.SDL_GameControllerOpen(i)
            if ctrl:
                controllers.append(ctrl)
        else:
            joy = sdl.SDL_JoystickOpen(i)
            if joy:
                joysticks.append(joy)

    config = AppConfig()
    evdev = LinuxInputReader()
    weather_loc = WeatherLocationFetcher(config)

    window = sdl.SDL_CreateWindow(
        b"AlexClock", 0, 0, 640, 480, SDL_WINDOW_FULLSCREEN_DESKTOP
    )
    renderer = sdl.SDL_CreateRenderer(
        ctypes.c_void_p(window), -1, SDL_RENDERER_ACCELERATED
    )

    width, height = ctypes.c_int(), ctypes.c_int()
    sdl.SDL_GetRendererOutputSize(
        ctypes.c_void_p(renderer), ctypes.byref(width), ctypes.byref(height)
    )
    W, H = width.value, height.value

    font_path = find_font()
    if not font_path:
        sys.exit(1)

    font_time = ttf.TTF_OpenFont(font_path, int(W * 0.19))
    font_sec = ttf.TTF_OpenFont(font_path, int(W * 0.080))
    font_date = ttf.TTF_OpenFont(font_path, int(W * 0.044))
    font_loc = ttf.TTF_OpenFont(font_path, int(W * 0.030))
    font_weather = ttf.TTF_OpenFont(font_path, int(W * 0.044))
    font_details = ttf.TTF_OpenFont(font_path, int(W * 0.030))
    font_top = ttf.TTF_OpenFont(font_path, int(W * 0.032))
    font_hint = ttf.TTF_OpenFont(font_path, int(W * 0.020))

    c_main = SDL_Color(235, 240, 245, 255)
    c_sub = SDL_Color(165, 175, 190, 255)
    c_hint = SDL_Color(115, 125, 138, 255)

    backlight = BacklightController()
    event = ctypes.create_string_buffer(64)
    running = True

    last_bat_check = 0
    bat_percent = None
    bat_status = ""

    sdl_ctrl_pressed = set()
    sdl_joy_pressed = set()
    last_hat_val = 0
    last_lang_toggle = 0.0

    def trigger_lang_toggle():
        nonlocal last_lang_toggle
        now_m = time.monotonic()
        if now_m - last_lang_toggle >= 0.30:
            last_lang_toggle = now_m
            config.toggle_lang()

    # Защита 0.8 сек при старте: очищаем буферы ввода
    start_time = time.time()
    while time.time() - start_time < 0.8:
        while sdl.SDL_PollEvent(event):
            pass
        evdev.poll()
        sdl.SDL_Delay(20)

    while running:
        while sdl.SDL_PollEvent(event):
            ev_type = ctypes.cast(event, ctypes.POINTER(ctypes.c_uint32)).contents.value

            if ev_type == SDL_QUIT:
                running = False

            elif ev_type == SDL_CONTROLLERBUTTONDOWN:
                btn_ev = ctypes.cast(event, ctypes.POINTER(SDL_ControllerButtonEvent)).contents
                btn = btn_ev.button
                sdl_ctrl_pressed.add(btn)

                if btn == SDL_CONTROLLER_BUTTON_DPAD_UP:
                    backlight.change(+10)
                elif btn == SDL_CONTROLLER_BUTTON_DPAD_DOWN:
                    backlight.change(-10)
                elif btn in (
                    SDL_CONTROLLER_BUTTON_DPAD_LEFT,
                    SDL_CONTROLLER_BUTTON_DPAD_RIGHT,
                    SDL_CONTROLLER_BUTTON_LEFTSHOULDER,
                    SDL_CONTROLLER_BUTTON_RIGHTSHOULDER,
                ):
                    trigger_lang_toggle()
                elif (SDL_CONTROLLER_BUTTON_GUIDE in sdl_ctrl_pressed and
                      SDL_CONTROLLER_BUTTON_START in sdl_ctrl_pressed):
                    running = False

            elif ev_type == SDL_CONTROLLERBUTTONUP:
                btn_ev = ctypes.cast(event, ctypes.POINTER(SDL_ControllerButtonEvent)).contents
                sdl_ctrl_pressed.discard(btn_ev.button)

            elif ev_type == SDL_JOYBUTTONDOWN:
                btn_ev = ctypes.cast(event, ctypes.POINTER(SDL_ControllerButtonEvent)).contents
                btn = btn_ev.button
                sdl_joy_pressed.add(btn)
                if ((6 in sdl_joy_pressed and 7 in sdl_joy_pressed) or
                    (8 in sdl_joy_pressed and 9 in sdl_joy_pressed) or
                    (10 in sdl_joy_pressed and 7 in sdl_joy_pressed)):
                    running = False

            elif ev_type == SDL_JOYBUTTONUP:
                btn_ev = ctypes.cast(event, ctypes.POINTER(SDL_ControllerButtonEvent)).contents
                sdl_joy_pressed.discard(btn_ev.button)

            elif ev_type == SDL_JOYHATMOTION:
                hat_ev = ctypes.cast(event, ctypes.POINTER(SDL_JoyHatEvent)).contents
                val = hat_ev.value
                if last_hat_val == 0 and val != 0:
                    if val & SDL_HAT_UP:
                        backlight.change(+10)
                    elif val & SDL_HAT_DOWN:
                        backlight.change(-10)
                    elif val & (SDL_HAT_LEFT | SDL_HAT_RIGHT):
                        trigger_lang_toggle()
                last_hat_val = val

            elif ev_type == SDL_KEYDOWN:
                sym = ctypes.cast(ctypes.byref(event, 20), ctypes.POINTER(ctypes.c_int32)).contents.value
                if sym == SDLK_UP:
                    backlight.change(+10)
                elif sym == SDLK_DOWN:
                    backlight.change(-10)
                elif sym in (SDLK_LEFT, SDLK_RIGHT):
                    trigger_lang_toggle()
                elif sym == SDLK_ESCAPE:
                    running = False

        for act in evdev.poll():
            if act == "EXIT":
                running = False
            elif act == "UP":
                backlight.change(+10)
            elif act == "DOWN":
                backlight.change(-10)
            elif act == "LANG":
                trigger_lang_toggle()

        now_ts = time.time()
        if now_ts - last_bat_check >= 5:
            last_bat_check = now_ts
            bat_percent, bat_status = get_battery_info()

        lang = config.get("lang", "en")
        tr = TRANSLATIONS.get(lang, TRANSLATIONS["en"])

        if bat_percent is not None:
            if bat_status == "Charging":
                bat_text = f"{tr['charge']}: {bat_percent}% (+)"
            elif bat_status == "Full":
                bat_text = f"{tr['charge']}: {bat_percent}% ({tr['full']})"
            else:
                bat_text = f"{tr['charge']}: {bat_percent}%"
        else:
            bat_text = f"{tr['charge']}: {tr['na']}"

        now = time.localtime(now_ts)
        hm_str = time.strftime("%H:%M", now)
        secs_str = time.strftime("%S", now)

        day_str = tr["days"][now.tm_wday]
        date_str = f"{time.strftime('%d.%m.%Y', now)}  ({day_str})"
        bright_str = f"{tr['bright']}: {backlight.percent}%"

        sdl.SDL_SetRenderDrawColor(ctypes.c_void_p(renderer), 18, 22, 30, 255)
        sdl.SDL_RenderClear(ctypes.c_void_p(renderer))

        draw_text(renderer, font_top, bright_str, c_sub, int(W * 0.04), int(H * 0.07), align="left")
        draw_text(renderer, font_top, bat_text, c_sub, W - int(W * 0.04), int(H * 0.07), align="right")

        draw_clock_with_seconds(
            renderer, font_time, font_sec,
            hm_str, secs_str,
            c_main, c_sub, W // 2, int(H * 0.32)
        )
        draw_text(renderer, font_date, date_str, c_sub, W // 2, int(H * 0.51))
        draw_text(renderer, font_loc, weather_loc.get_location_text(lang), c_hint, W // 2, int(H * 0.60))
        draw_text(renderer, font_weather, weather_loc.get_weather_text(lang), c_main, W // 2, int(H * 0.70))
        draw_text(renderer, font_details, weather_loc.get_details_text(lang), c_sub, W // 2, int(H * 0.79))

        draw_text(renderer, font_hint, tr["hint"], c_hint, W // 2, int(H * 0.91))

        sdl.SDL_RenderPresent(ctypes.c_void_p(renderer))
        sdl.SDL_Delay(50)

    evdev.close()
    ttf.TTF_CloseFont(ctypes.c_void_p(font_time))
    ttf.TTF_CloseFont(ctypes.c_void_p(font_sec))
    ttf.TTF_CloseFont(ctypes.c_void_p(font_date))
    ttf.TTF_CloseFont(ctypes.c_void_p(font_loc))
    ttf.TTF_CloseFont(ctypes.c_void_p(font_weather))
    ttf.TTF_CloseFont(ctypes.c_void_p(font_details))
    ttf.TTF_CloseFont(ctypes.c_void_p(font_top))
    ttf.TTF_CloseFont(ctypes.c_void_p(font_hint))
    sdl.SDL_DestroyRenderer(ctypes.c_void_p(renderer))
    sdl.SDL_DestroyWindow(ctypes.c_void_p(window))
    ttf.TTF_Quit()
    sdl.SDL_Quit()

if __name__ == "__main__":
    main()
