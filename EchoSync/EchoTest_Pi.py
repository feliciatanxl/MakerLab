import serial
import json
import time
import subprocess
import wave
import audioop
import os
import html
import requests
import concurrent.futures
import re
from datetime import datetime

# ==========================
# EchoSync Configuration
# ==========================

ARDUINO_PORT = "/dev/ttyUSB0"
BAUD_RATE = 115200

MIC_DEVICE = "plughw:1,0"

# Store generated audio in the current user's home folder instead of /tmp.
# This avoids permission issues when a previous run created /tmp files as root.
AUDIO_DIR = os.path.join(os.path.expanduser("~"), "echosync_audio")
os.makedirs(AUDIO_DIR, exist_ok=True)
RECORD_FILE = os.path.join(AUDIO_DIR, "echosync_response.wav")
TTS_FILE = os.path.join(AUDIO_DIR, "echosync_tts.wav")

GB10_URL = "http://172.20.10.3:8000/v1/chat/completions"
GB10_MODEL = "meta/llama-3.1-8b-instruct"

# Send alerts to personal laptop, Dell laptop, and OpenShift at the same time.
# Both local laptops must run:
#   npm run dev -- -H 0.0.0.0
PERSONAL_LAPTOP_BASE_URL = "http://172.20.10.5:3000"
DELL_LAPTOP_BASE_URL = "http://172.20.10.2:3000"
OPENSHIFT_BASE_URL = "https://echosync-echosync.apps.innovate.sg-aie.com"

ALL_BASE_URLS = [
    PERSONAL_LAPTOP_BASE_URL,
    DELL_LAPTOP_BASE_URL,
    OPENSHIFT_BASE_URL,
]

DASHBOARD_APIS = [
    f"{base}/api/sensor-alert" for base in ALL_BASE_URLS
]

CAREGIVER_APIS = [
    f"{base}/api/caregiver-alert" for base in ALL_BASE_URLS
]

MYRESPONDER_APIS = [
    f"{base}/api/myresponder-alert" for base in ALL_BASE_URLS
]

# Node control checks all three.
# Pause is merged safely: if ANY device pauses the node, the Pi pauses.
# Language is selected from the most recently updated control state when available;
# otherwise, the first non-default language found across the three devices is used.
NODE_CONTROL_APIS = [
    f"{base}/api/node-control" for base in ALL_BASE_URLS
]

# Speed settings for demo:
# - Local laptop URLs can hang if the laptop is off / npm is not running / IP changed.
# - Keep timeouts short so one unreachable URL does not freeze the Pi.
NODE_CONTROL_FAST_TIMEOUT = 0.35
NODE_CONTROL_FULL_TIMEOUT = 0.8
ALERT_POST_TIMEOUT = 2.0
GB10_TIMEOUT = 8
HTTP_WORKERS = max(1, len(ALL_BASE_URLS))

SPEECH_KEY = os.environ.get("SPEECH_KEY")
SPEECH_REGION = os.environ.get("SPEECH_REGION", "southeastasia")
USE_AZURE_TTS = True
USE_AZURE_STT = True

DEFAULT_LANGUAGE = "en"

VOICE_THRESHOLD = 150
ALERT_COOLDOWN = 30
FALL_REARM_SECONDS = 5

# ==========================
# Arduino LCD Configuration
# ==========================
# LCD is connected to Arduino, not Raspberry Pi.
# Raspberry Pi sends LCD commands over the same USB Serial line:
# LCD:LINE1|LINE2
#
# Arduino must receive this command and display it on the I2C LCD.

ARDUINO_LCD_ENABLED = True

# ==========================
# Sensor Decision Thresholds
# ==========================

SOUND_THRESHOLD = 10
SOUND_MARGIN = 3
SOUND_HOLD_SECONDS = 2.0

GROUND_FALL_SOUND_WINDOW = 0.8

# Bed/load fall pairing window:
# Allows loud sound + sudden load change to happen in either order.
# Example supported:
#   1) sound first, then load change
#   2) load change first, then sound
# Both must happen close together within this window.
LOAD_SOUND_PAIR_WINDOW = 2.0

NEAR_DISTANCE_CM = 50
DISTANCE_JUMP_CM = 20
GROUND_DISTANCE_CHANGE_CM = 20
DISTANCE_HOLD_SECONDS = 1.5

LOAD_PRESENT_THRESHOLD = 5000
LOAD_SUDDEN_DELTA = 8000
LOAD_HOLD_SECONDS = 2.0

DIRECT_HELP_LISTENING = True
HELP_LISTEN_INTERVAL = 2
HELP_RECORD_SECONDS = 5
HELP_VOICE_RMS_THRESHOLD = 60

# Prevent the 5-second direct-help microphone recording from blocking
# the Arduino sensor loop during a possible load/sound fall pattern.
# This protects the load+sound pairing window during demo.
SKIP_DIRECT_HELP_DURING_SENSOR_ACTIVITY = True

# If Azure STT cannot transcribe short pain sounds like "ow" or "ah",
# a loud unclear voice can still start the EchoSync check-in.
PAIN_SOUND_VOICE_THRESHOLD = 120

# Once direct-help hears a help/pain word, it will not keep re-detecting
# again until this rearm window has passed.
DIRECT_HELP_REARM_SECONDS = 30

# Demo helper:
# Allows a real low-confidence sensor alert to be sent for testing.
# This does not remove or change the existing Medium/High/Critical logic.
LOW_RISK_DEMO_ALERTS = False
LOW_RISK_DEMO_COOLDOWN = 30
LOW_RISK_STABLE_SECONDS = 3
LOW_RISK_ALLOW_NORMAL_STABLE = False



# ==========================
# Helper
# ==========================

def safe_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def safe_bool(value, default=False):
    """
    Accepts booleans from the API even if they arrive as true/false,
    1/0, or string values. This is only used for node-control merging.
    """
    if isinstance(value, bool):
        return value

    if value is None:
        return default

    text = str(value).strip().lower()

    if text in ["1", "true", "yes", "y", "on"]:
        return True

    if text in ["0", "false", "no", "n", "off"]:
        return False

    return default


def get_control_timestamp(data):
    """
    Optional helper for multi-device node control.
    If the API gives updatedAt/timestamp/lastUpdated, EchoSync can choose
    the most recently changed language across personal laptop, Dell and OpenShift.
    """
    for key in ["updatedAt", "lastUpdated", "timestamp", "controlUpdatedAt"]:
        value = data.get(key)

        if not value:
            continue

        try:
            if isinstance(value, (int, float)):
                # Support either seconds or milliseconds.
                return float(value) / 1000 if value > 100000000000 else float(value)

            text = str(value).replace("Z", "+00:00")
            return datetime.fromisoformat(text).timestamp()

        except Exception:
            continue

    return None


def normalize_language(value):
    if not value:
        return DEFAULT_LANGUAGE

    lang = str(value).strip().lower()

    if lang in ["en", "english", "singapore english", "sg english"]:
        return "en"

    if lang in ["zh", "chinese", "mandarin", "mandarin chinese"]:
        return "zh"

    if lang in ["ms", "malay", "bahasa melayu"]:
        return "ms"

    if lang in ["ta", "tamil"]:
        return "ta"

    return DEFAULT_LANGUAGE


def cleanup_and_exit():
    print("Cleaning up...")

    try:
        lcd_display("ECHOSYNC", "STOPPED", force=True)
    except Exception:
        pass

    try:
        subprocess.run(["pkill", "arecord"], check=False)
    except Exception:
        pass

    print("Stopped")


# ==========================
# Arduino Serial LCD Helper
# ==========================
# This DOES NOT use Raspberry Pi I2C.
# It only sends short messages to Arduino over Serial.
#
# Arduino must listen for:
# LCD:LINE1|LINE2

last_lcd_message = ("", "")
last_lcd_update_time = 0


def lcd_display(line1, line2="", force=False):
    global last_lcd_message, last_lcd_update_time

    if not ARDUINO_LCD_ENABLED:
        return

    try:
        line1 = str(line1).replace("\n", " ")[:16]
        line2 = str(line2).replace("\n", " ")[:16]

        now = time.time()
        message = (line1, line2)

        # Avoid sending the exact same message too many times
        if not force:
            if message == last_lcd_message and now - last_lcd_update_time < 1:
                return

        last_lcd_message = message
        last_lcd_update_time = now

        if "ser" not in globals() or ser is None:
            return

        command = f"LCD:{line1}|{line2}\n"
        ser.write(command.encode("utf-8"))

    except Exception as e:
        print("Arduino LCD send error:", e)


def get_test_case_lcd(sensor_data):
    direct_help_request = safe_int(sensor_data.get("directHelpRequest", 0))
    sleeping_likely = safe_int(sensor_data.get("sleepingLikely", 0))
    clap_likely = safe_int(sensor_data.get("clapLikely", 0))
    bed_fall_likely = safe_int(sensor_data.get("bedFallLikely", 0))
    ground_fall_likely = safe_int(sensor_data.get("groundFallLikely", 0))

    near_detected = safe_int(sensor_data.get("nearDetected", 0))
    sound_detected = safe_int(sensor_data.get("soundDetected", 0))
    fresh_sound_for_fall = safe_int(sensor_data.get("freshSoundForFall", 0))
    distance_jump = safe_int(sensor_data.get("distanceJump", 0))
    load_sudden_change = safe_int(sensor_data.get("loadSuddenChange", 0))
    possible_fall = safe_int(sensor_data.get("possibleFall", 0))

    if direct_help_request == 1:
        return "TC12 HELP", "CHECK-IN"

    if bed_fall_likely == 1:
        return "TC07 BED FALL", "CHECK-IN"

    if ground_fall_likely == 1:
        return "TC08 FLOORFALL", "CHECK-IN"

    if sleeping_likely == 1:
        return "TC05 RESTING", "NO ALERT"

    if clap_likely == 1:
        return "TC03 CLAP/BG NOISE", "NO ALERT"

    if load_sudden_change == 1 and fresh_sound_for_fall == 0 and possible_fall == 0:
        return "TC06 BED MOVE", "NO ALERT"

    if sound_detected == 1 and fresh_sound_for_fall == 0 and distance_jump == 1:
        return "TC04 OLD SOUND", "NO ALERT"

    if near_detected == 1 and fresh_sound_for_fall == 0 and possible_fall == 0:
        return "TC02 NEAR ONLY", "NO ALERT"

    return "TC01 NORMAL", "MONITORING"


def print_sensor_screen(sensor_data):
    """
    Printing helper only.
    This does not change detection, risk, voice check-in, routing, or payload data.
    It only makes the Raspberry Pi terminal easier to read during demo.
    """
    sound_level = safe_int(sensor_data.get("soundLevel", 0))
    sound_baseline = safe_int(sensor_data.get("soundBaseline", 0))
    raw_sound_detected = safe_int(sensor_data.get("rawSoundDetected", 0))
    sound_detected = safe_int(sensor_data.get("soundDetected", 0))
    fresh_sound_for_fall = safe_int(sensor_data.get("freshSoundForFall", 0))
    mic_digital = safe_int(sensor_data.get("micDigital", 0))

    pir_motion = safe_int(sensor_data.get("pirMotion", 0))
    pir_motion_stopped = safe_int(sensor_data.get("pirMotionStopped", 0))

    distance_cm = sensor_data.get("distanceCm", -1)
    distance_change = safe_int(sensor_data.get("distanceChange", 0))
    distance_jump = safe_int(sensor_data.get("distanceJump", 0))
    near_detected = safe_int(sensor_data.get("nearDetected", 0))

    load_ready = safe_int(sensor_data.get("loadReady", 0))
    load_net = safe_int(sensor_data.get("loadNet", 0))
    load_detected = safe_int(sensor_data.get("loadDetected", 0))
    load_change = safe_int(sensor_data.get("loadChange", 0))
    load_sudden_change = safe_int(sensor_data.get("loadSuddenChange", 0))
    load_sound_combo = safe_int(sensor_data.get("loadSoundCombo", 0))

    sleeping_likely = safe_int(sensor_data.get("sleepingLikely", 0))
    clap_likely = safe_int(sensor_data.get("clapLikely", 0))
    bed_fall_likely = safe_int(sensor_data.get("bedFallLikely", 0))
    ground_fall_likely = safe_int(sensor_data.get("groundFallLikely", 0))
    ground_fall_strong = safe_int(sensor_data.get("groundFallStrong", 0))

    possible_fall = safe_int(sensor_data.get("possibleFall", 0))
    direct_help_request = safe_int(sensor_data.get("directHelpRequest", 0))
    alert = safe_int(sensor_data.get("alert", 0))

    triggered = []

    if raw_sound_detected == 1:
        triggered.append("SOUND RAW")
    elif sound_detected == 1:
        triggered.append("SOUND HELD")

    if pir_motion == 1:
        triggered.append("PIR MOTION")

    if near_detected == 1:
        triggered.append("NEAR OBJECT")

    if distance_jump == 1:
        triggered.append("DISTANCE JUMP")

    if load_detected == 1:
        triggered.append("LOAD PRESENT")

    if load_sudden_change == 1:
        triggered.append("LOAD SUDDEN")

    if load_sound_combo == 1:
        triggered.append("LOAD+SOUND COMBO")

    if direct_help_request == 1:
        triggered.append("DIRECT HELP")

    if possible_fall == 1:
        triggered.append("POSSIBLE FALL")

    triggered_text = ", ".join(triggered) if triggered else "none"

    sound_state = "TRIGGERED" if raw_sound_detected == 1 or sound_detected == 1 else "normal"
    sound_meaning = (
        "above impact trigger"
        if sound_level >= SOUND_THRESHOLD or mic_digital == 1 or raw_sound_detected == 1
        else "below impact trigger"
    )

    pir_state = "motion" if pir_motion == 1 else "no motion"
    near_state = "NEAR" if near_detected == 1 else "clear"
    jump_state = "JUMP" if distance_jump == 1 else "stable"
    load_state = "PRESENT" if load_detected == 1 else "no presence"
    sudden_state = "SUDDEN" if load_sudden_change == 1 else "stable"

    print("")
    print("========== EchoSync Pi Sensor Screen ==========")
    print(f"Triggered now : {triggered_text}")
    print(f"Decision      : possibleFall={possible_fall} | alert={alert} | directHelp={direct_help_request}")
    print("-----------------------------------------------")
    print(
        "Sound sensor : "
        f"{sound_state} | reading {sound_level}, baseline {sound_baseline}, "
        f"impact trigger >= {SOUND_THRESHOLD}, margin +{SOUND_MARGIN}, "
        f"{sound_meaning}, raw={raw_sound_detected}, held={sound_detected}, "
        f"freshFall={fresh_sound_for_fall}, micDigital={mic_digital}"
    )
    print(
        "PIR / Motion : "
        f"{pir_state} | motion={pir_motion}, stopped={pir_motion_stopped}"
    )
    print(
        "Ultrasonic   : "
        f"{near_state}, {jump_state} | distance {distance_cm} cm, "
        f"near trigger <= {NEAR_DISTANCE_CM} cm, change {distance_change} cm, "
        f"jump trigger > {DISTANCE_JUMP_CM} cm"
    )
    print(
        "Load sensor  : "
        f"{load_state}, {sudden_state} | ready={load_ready}, reading {load_net}, "
        f"change {load_change}, presence trigger >= {LOAD_PRESENT_THRESHOLD}, "
        f"sudden trigger >= {LOAD_SUDDEN_DELTA}"
    )
    print(
        "Pattern flags: "
        f"sleeping={sleeping_likely} | clap/noise={clap_likely} | "
        f"loadSoundCombo={load_sound_combo} | "
        f"bedFall={bed_fall_likely} | groundFall={ground_fall_likely} | "
        f"groundStrong={ground_fall_strong}"
    )
    print("===============================================")
    print("")


# ==========================
# Sensor Decision Logic
# ==========================

previous_load_net = None
previous_distance_cm = None
previous_pir_motion = None

sound_baseline = None
last_sound_time = 0
last_distance_jump_time = 0
last_load_sudden_time = 0
last_help_listen_time = 0

low_risk_candidate_since = None
last_low_risk_demo_time = 0


def enrich_sensor_data(sensor_data):
    global previous_load_net, previous_distance_cm, previous_pir_motion
    global sound_baseline, last_sound_time, last_distance_jump_time, last_load_sudden_time

    now = time.time()

    sound_level = safe_int(sensor_data.get("soundLevel", 0))
    mic_digital = safe_int(sensor_data.get("micDigital", 0))
    pir_motion = safe_int(sensor_data.get("pirMotion", 0))
    distance_cm = safe_int(sensor_data.get("distanceCm", -1), -1)

    load_ready = safe_int(sensor_data.get("loadReady", 0))
    load_net = safe_int(sensor_data.get("loadNet", 0))

    if sound_baseline is None:
        sound_baseline = sound_level
    else:
        if sound_level < sound_baseline + SOUND_MARGIN:
            sound_baseline = int((sound_baseline * 0.9) + (sound_level * 0.1))

    raw_sound_detected = 0

    if mic_digital == 1:
        raw_sound_detected = 1

    elif sound_level >= SOUND_THRESHOLD:
        raw_sound_detected = 1

    elif sound_baseline is not None and sound_level >= sound_baseline + SOUND_MARGIN:
        raw_sound_detected = 1

    if raw_sound_detected == 1:
        last_sound_time = now

    sound_detected = 1 if now - last_sound_time <= SOUND_HOLD_SECONDS else 0
    fresh_sound_for_fall = 1 if now - last_sound_time <= GROUND_FALL_SOUND_WINDOW else 0

    near_detected = 0
    if 0 < distance_cm <= NEAR_DISTANCE_CM:
        near_detected = 1

    distance_change = 0

    if (
        previous_distance_cm is not None
        and previous_distance_cm > 0
        and distance_cm > 0
    ):
        distance_change = abs(distance_cm - previous_distance_cm)

        if distance_change > DISTANCE_JUMP_CM:
            last_distance_jump_time = now

    distance_jump = 1 if now - last_distance_jump_time <= DISTANCE_HOLD_SECONDS else 0

    load_detected = 0
    if load_ready == 1 and abs(load_net) > LOAD_PRESENT_THRESHOLD:
        load_detected = 1

    load_change = 0

    if previous_load_net is not None and load_ready == 1:
        load_change = abs(load_net - previous_load_net)

        if load_change > LOAD_SUDDEN_DELTA:
            last_load_sudden_time = now

    load_sudden_change = 1 if now - last_load_sudden_time <= LOAD_HOLD_SECONDS else 0

    recent_sound_for_load = 1 if (
        last_sound_time > 0
        and now - last_sound_time <= LOAD_SOUND_PAIR_WINDOW
    ) else 0

    recent_load_for_sound = 1 if (
        last_load_sudden_time > 0
        and now - last_load_sudden_time <= LOAD_SOUND_PAIR_WINDOW
    ) else 0

    # Supports BOTH directions for bed/load fall detection:
    # 1) loud sound first, then sudden load change
    # 2) sudden load change first, then loud sound
    load_sound_combo = 1 if (
        recent_sound_for_load == 1
        and recent_load_for_sound == 1
    ) else 0

    pir_motion_stopped = 0

    if previous_pir_motion is not None:
        if previous_pir_motion == 1 and pir_motion == 0:
            pir_motion_stopped = 1

    sleeping_likely = 0

    if (
        load_detected == 1
        and load_sudden_change == 0
        and recent_load_for_sound == 0
        and recent_sound_for_load == 0
        and sound_detected == 0
        and distance_jump == 0
    ):
        sleeping_likely = 1

    clap_likely = 0

    if (
        sound_detected == 1
        and load_sudden_change == 0
        and recent_load_for_sound == 0
        and load_sound_combo == 0
        and distance_jump == 0
    ):
        clap_likely = 1

    bed_fall_likely = 0

    if load_sound_combo == 1:
        bed_fall_likely = 1

    elif load_sudden_change == 1 and distance_jump == 1:
        bed_fall_likely = 1

    ground_fall_likely = 0

    if load_detected == 0 and fresh_sound_for_fall == 1:
        if distance_jump == 1 and distance_change >= GROUND_DISTANCE_CHANGE_CM:
            ground_fall_likely = 1

    ground_fall_strong = 0

    if (
        ground_fall_likely == 1
        and (
            pir_motion == 0
            or pir_motion_stopped == 1
        )
    ):
        ground_fall_strong = 1

    possible_fall = 0

    if bed_fall_likely == 1:
        possible_fall = 1

    elif ground_fall_likely == 1:
        possible_fall = 1

    # Noise filters should only suppress the alert when there is NO actual
    # fall evidence. Previously, clapLikely/sleepingLikely could cancel
    # a valid load+sound combo after bedFallLikely was already detected.
    if (
        sleeping_likely == 1 or clap_likely == 1
    ) and bed_fall_likely == 0 and ground_fall_likely == 0:
        possible_fall = 0

    alert = possible_fall

    sensor_data["soundLevel"] = sound_level
    sensor_data["micDigital"] = mic_digital
    sensor_data["soundBaseline"] = sound_baseline
    sensor_data["rawSoundDetected"] = raw_sound_detected
    sensor_data["soundDetected"] = sound_detected
    sensor_data["freshSoundForFall"] = fresh_sound_for_fall

    sensor_data["nearDetected"] = near_detected

    sensor_data["loadDetected"] = load_detected
    sensor_data["loadChange"] = load_change
    sensor_data["loadSuddenChange"] = load_sudden_change
    sensor_data["recentSoundForLoad"] = recent_sound_for_load
    sensor_data["recentLoadForSound"] = recent_load_for_sound
    sensor_data["loadSoundCombo"] = load_sound_combo

    sensor_data["distanceChange"] = distance_change
    sensor_data["distanceJump"] = distance_jump

    sensor_data["pirMotionStopped"] = pir_motion_stopped

    sensor_data["sleepingLikely"] = sleeping_likely
    sensor_data["clapLikely"] = clap_likely

    sensor_data["bedFallLikely"] = bed_fall_likely
    sensor_data["groundFallLikely"] = ground_fall_likely
    sensor_data["groundFallStrong"] = ground_fall_strong

    sensor_data["directHelpRequest"] = safe_int(sensor_data.get("directHelpRequest", 0))
    sensor_data["possibleFall"] = possible_fall
    sensor_data["alert"] = alert

    previous_load_net = load_net
    previous_distance_cm = distance_cm
    previous_pir_motion = pir_motion

    return sensor_data


# ==========================
# Startup
# ==========================

ser = None

if not os.path.exists(ARDUINO_PORT):
    raise RuntimeError(f"Arduino port not found: {ARDUINO_PORT}")

ser = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=1, write_timeout=1)

# Opening Serial usually resets Arduino. Give it time before sending LCD command.
time.sleep(2)

last_alert_time = 0

fall_latched = False
fall_normal_since = None

direct_help_latched = False
direct_help_latched_time = 0

print("===================================")
print("EchoSync Full Demo Started")
print("Arduino:", ARDUINO_PORT)
print("Mic:", MIC_DEVICE)
print("Record file:", RECORD_FILE)
print("TTS file:", TTS_FILE)
print("GB10:", GB10_URL)
print("Dashboard APIs:", DASHBOARD_APIS)
print("Caregiver APIs:", CAREGIVER_APIS)
print("myResponder APIs:", MYRESPONDER_APIS)
print("Node Control APIs:", NODE_CONTROL_APIS)
print("Default language:", DEFAULT_LANGUAGE)
print("Arduino LCD over Serial:", "ON" if ARDUINO_LCD_ENABLED else "OFF")
print("===================================")

if SPEECH_KEY:
    print("Azure Speech: Enabled")
    print("Azure region:", SPEECH_REGION)
else:
    print("Azure Speech: No key found, using fallback voice-level only")

lcd_display("ECHOSYNC", "READY", force=True)



# ==========================
# Node Pause / Speech Guard
# ==========================

def is_node_paused_for_speech():
    """
    Fast pause check used before/during speaker playback.

    It checks personal laptop, Dell laptop and OpenShift in parallel so one
    unreachable URL does not make the speaker/check-in feel frozen.
    """
    if not NODE_CONTROL_APIS:
        return False

    def fetch_control(url):
        try:
            response = requests.get(url, timeout=NODE_CONTROL_FAST_TIMEOUT)

            if response.status_code != 200:
                return url, None

            return url, response.json()

        except Exception:
            return url, None

    reached_any_control = False

    with concurrent.futures.ThreadPoolExecutor(max_workers=HTTP_WORKERS) as executor:
        futures = [executor.submit(fetch_control, url) for url in NODE_CONTROL_APIS]

        for future in concurrent.futures.as_completed(futures):
            url, data = future.result()

            if not data:
                continue

            reached_any_control = True

            if not safe_bool(data.get("sensorMonitoringEnabled", True), True):
                print("Node pause detected from:", url)
                return True

    if not reached_any_control:
        # If the pause API cannot be reached, do not block the demo by accident.
        return False

    return False


def play_command_with_pause_watch(command, stop_if_node_paused=False):
    if not stop_if_node_paused:
        subprocess.run(command, check=False)
        return True

    if is_node_paused_for_speech():
        print("Node is paused by caregiver. Speaker playback skipped.")
        lcd_display("NODE PAUSED", "VOICE SKIPPED", force=True)
        return False

    process = subprocess.Popen(command)

    try:
        while process.poll() is None:
            if is_node_paused_for_speech():
                print("Node paused during voice playback. Stopping speaker.")
                lcd_display("NODE PAUSED", "VOICE STOPPED", force=True)

                process.terminate()

                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()

                return False

            time.sleep(0.5)

        return True

    except Exception as e:
        print("Speaker playback monitor error:", e)

        try:
            process.kill()
        except Exception:
            pass

        return False


# ==========================
# Azure TTS
# ==========================

def speak(text, voice="en-SG-LunaNeural", lang="en-SG", stop_if_node_paused=False):
    print("Speaker:", text)

    if stop_if_node_paused and is_node_paused_for_speech():
        print("Node is paused by caregiver. Speaker skipped before playback.")
        lcd_display("NODE PAUSED", "VOICE SKIPPED", force=True)
        return False

    if USE_AZURE_TTS and SPEECH_KEY:
        try:
            url = f"https://{SPEECH_REGION}.tts.speech.microsoft.com/cognitiveservices/v1"

            safe_text = html.escape(text)

            ssml = f"""
<speak version="1.0" xml:lang="{lang}">
  <voice name="{voice}">
    {safe_text}
  </voice>
</speak>
"""

            headers = {
                "Ocp-Apim-Subscription-Key": SPEECH_KEY,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "riff-16khz-16bit-mono-pcm",
                "User-Agent": "EchoSync-RaspberryPi",
            }

            response = requests.post(
                url,
                headers=headers,
                data=ssml.encode("utf-8"),
                timeout=20,
            )

            if response.status_code == 200:
                with open(TTS_FILE, "wb") as f:
                    f.write(response.content)

                if stop_if_node_paused and is_node_paused_for_speech():
                    print("Node was paused after TTS generation. Check-in audio will not play.")
                    lcd_display("NODE PAUSED", "VOICE SKIPPED", force=True)
                    return False

                return play_command_with_pause_watch(
                    ["aplay", TTS_FILE],
                    stop_if_node_paused=stop_if_node_paused,
                )

            print("Azure TTS error:", response.status_code, response.text)

        except Exception as e:
            print("Azure TTS failed, using espeak fallback:", e)

    return play_command_with_pause_watch(
        ["espeak", text],
        stop_if_node_paused=stop_if_node_paused,
    )


def get_checkin_prompt(preferred_language):
    language = normalize_language(preferred_language)

    prompts = {
        "en": {
            "text": "EchoSync check-in. Are you okay? If you are okay, say I am okay. If you need help, say help.",
            "voice": "en-SG-LunaNeural",
            "lang": "en-SG",
            "label": "English",
        },
        "zh": {
            "text": "你还好吗？如果没事，请说我没事。如果需要帮忙，请说救命。",
            "voice": "zh-CN-XiaoxiaoNeural",
            "lang": "zh-CN",
            "label": "Mandarin",
        },
        "ms": {
            "text": "Awak okay? Kalau okay, cakap saya okay. Kalau perlukan bantuan, cakap tolong.",
            "voice": "ms-MY-YasminNeural",
            "lang": "ms-MY",
            "label": "Malay",
        },
        "ta": {
            "text": "Neenga okay-aa? Okay-na naan okay nu sollunga. Help venumna help nu sollunga.",
            "voice": "ta-SG-VenbaNeural",
            "lang": "ta-SG",
            "label": "Tamil",
        },
    }

    return prompts.get(language, prompts["en"])


def get_response_prompt(preferred_language, voice_intent):
    language = normalize_language(preferred_language)

    if voice_intent == "ok":
        prompts = {
            "en": ("Response detected. Alert lowered to low risk for caregiver monitoring.", "en-SG-LunaNeural", "en-SG"),
            "zh": ("已检测到回应。警报已降为低风险，并交由照护者留意。", "zh-CN-XiaoxiaoNeural", "zh-CN"),
            "ms": ("Respons dikesan. Amaran diturunkan kepada risiko rendah untuk pemantauan penjaga.", "ms-MY-YasminNeural", "ms-MY"),
            "ta": ("Response detected. Alert low risk-aa maathappattathu for caregiver monitoring.", "ta-SG-VenbaNeural", "ta-SG"),
        }
    elif voice_intent == "help":
        prompts = {
            "en": ("Help request confirmed. Escalating alert for emergency review.", "en-SG-LunaNeural", "en-SG"),
            "zh": ("检测到求救。警报将升级处理。", "zh-CN-XiaoxiaoNeural", "zh-CN"),
            "ms": ("Permintaan bantuan disahkan. Amaran akan dinaikkan untuk semakan kecemasan.", "ms-MY-YasminNeural", "ms-MY"),
            "ta": ("Help request confirmed. Alert emergency review-ku escalate pannapadum.", "ta-SG-VenbaNeural", "ta-SG"),
        }
    elif voice_intent == "unclear":
        prompts = {
            "en": ("Response unclear. Caregiver verification recommended.", "en-SG-LunaNeural", "en-SG"),
            "zh": ("回应不清楚。建议由照护者确认情况。", "zh-CN-XiaoxiaoNeural", "zh-CN"),
            "ms": ("Respons tidak jelas. Pengesahan penjaga disyorkan.", "ms-MY-YasminNeural", "ms-MY"),
            "ta": ("Response unclear. Caregiver verification recommended.", "ta-SG-VenbaNeural", "ta-SG"),
        }
    else:
        prompts = {
            "en": ("No response detected. Escalating alert for review.", "en-SG-LunaNeural", "en-SG"),
            "zh": ("没有检测到回应。警报将升级处理。", "zh-CN-XiaoxiaoNeural", "zh-CN"),
            "ms": ("Tiada respons dikesan. Amaran akan dinaikkan untuk semakan.", "ms-MY-YasminNeural", "ms-MY"),
            "ta": ("No response detected. Alert review-ku escalate pannapadum.", "ta-SG-VenbaNeural", "ta-SG"),
        }

    text, voice, lang = prompts.get(language, prompts["en"])

    return {
        "text": text,
        "voice": voice,
        "lang": lang,
    }


def get_direct_help_lcd_prompt(preferred_language):
    language = normalize_language(preferred_language)

    prompts = {
        "en": ("EN HELP LISTEN", "HELP/OW/AH"),
        "zh": ("ZH HELP LISTEN", "SAY JIU MING"),
        "ms": ("MS HELP LISTEN", "TOLONG/SAKIT"),
        "ta": ("TA HELP LISTEN", "UDAVI/VALI"),
    }

    return prompts.get(language, prompts["en"])


def get_direct_help_ack_prompt(preferred_language):
    language = normalize_language(preferred_language)

    prompts = {
        "en": {
            "text": "Help request heard. EchoSync will check on you now.",
            "voice": "en-SG-LunaNeural",
            "lang": "en-SG",
        },
        "zh": {
            "text": "已听到求助。EchoSync 现在会确认你的情况。",
            "voice": "zh-CN-XiaoxiaoNeural",
            "lang": "zh-CN",
        },
        "ms": {
            "text": "Permintaan bantuan dikesan. EchoSync akan periksa keadaan anda sekarang.",
            "voice": "ms-MY-YasminNeural",
            "lang": "ms-MY",
        },
        "ta": {
            "text": "Help request detected. EchoSync ippo unga nilamai check pannum.",
            "voice": "ta-SG-VenbaNeural",
            "lang": "ta-SG",
        },
    }

    return prompts.get(language, prompts["en"])


# ==========================
# Audio Recording / STT
# ==========================

def record_audio(seconds=5):
    print(f"Recording mic for {seconds} seconds...")
    print("Recording file:", RECORD_FILE)

    # Remove the previous recording first so Azure STT never reads stale audio.
    try:
        if os.path.exists(RECORD_FILE):
            os.remove(RECORD_FILE)
    except PermissionError:
        print("Recording file permission denied:", RECORD_FILE)
        print("Try: sudo rm -f", RECORD_FILE)
        lcd_display("MIC ERROR", "CHECK PERM", force=True)
        return False
    except Exception as e:
        print("Could not remove old recording:", e)

    result = subprocess.run(
        [
            "arecord",
            "-D", MIC_DEVICE,
            "-f", "S16_LE",
            "-r", "16000",
            "-c", "1",
            "-d", str(seconds),
            RECORD_FILE,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("arecord failed.")
        if result.stderr:
            print(result.stderr.strip())
        if result.stdout:
            print(result.stdout.strip())
        lcd_display("MIC ERROR", "ARECORD FAIL", force=True)
        return False

    if not os.path.exists(RECORD_FILE) or os.path.getsize(RECORD_FILE) == 0:
        print("Recording failed: output file missing or empty:", RECORD_FILE)
        lcd_display("MIC ERROR", "NO WAV FILE", force=True)
        return False

    return True


def get_voice_level():
    if not os.path.exists(RECORD_FILE):
        return 0

    try:
        with wave.open(RECORD_FILE, "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            return audioop.rms(frames, wav.getsampwidth())

    except Exception as e:
        print("Audio analysis error:", e)
        return 0


def get_stt_language(preferred_language):
    language = normalize_language(preferred_language)

    if language == "en":
        return "en-SG"

    if language == "zh":
        return "zh-CN"

    if language == "ms":
        return "ms-MY"

    if language == "ta":
        return "ta-IN"

    return "en-SG"


def transcribe_audio(preferred_language):
    if not USE_AZURE_STT:
        return ""

    if not SPEECH_KEY:
        print("Azure STT unavailable: no SPEECH_KEY")
        return ""

    if not os.path.exists(RECORD_FILE):
        print("Azure STT unavailable: no recording file")
        return ""

    try:
        stt_language = get_stt_language(preferred_language)

        url = (
            f"https://{SPEECH_REGION}.stt.speech.microsoft.com/"
            f"speech/recognition/conversation/cognitiveservices/v1"
            f"?language={stt_language}&format=simple"
        )

        headers = {
            "Ocp-Apim-Subscription-Key": SPEECH_KEY,
            "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
            "Accept": "application/json",
        }

        with open(RECORD_FILE, "rb") as audio:
            response = requests.post(
                url,
                headers=headers,
                data=audio,
                timeout=20,
            )

        if response.status_code != 200:
            print("Azure STT error:", response.status_code, response.text)
            return ""

        result = response.json()
        print("Azure STT result:", result)

        if result.get("RecognitionStatus") == "Success":
            return result.get("DisplayText", "").strip()

        return ""

    except Exception as e:
        print("Azure STT failed:", e)
        return ""


def is_latin_word_or_phrase(value):
    return re.fullmatch(r"[a-zA-Z0-9\s'!?.-]+", value or "") is not None


def contains_phrase(text, phrase):
    phrase = str(phrase).lower().strip()

    if not phrase:
        return False

    # For English/Malay/Tamil romanised words, use word boundaries.
    # This prevents short sounds like "ah" from matching inside longer words.
    if is_latin_word_or_phrase(phrase):
        pattern = r"\b" + re.escape(phrase) + r"\b"
        return re.search(pattern, text) is not None

    # For Chinese characters, normal substring matching works better.
    return phrase in text


def classify_voice_intent(transcript, voice_level, preferred_language=DEFAULT_LANGUAGE):
    text = transcript.lower().strip()
    language = normalize_language(preferred_language)

    help_words_by_language = {
        "en": [
            "help",
            "help me",
            "need help",
            "emergency",
            "ambulance",
            "call ambulance",
            "pain",
            "i am in pain",
            "i'm in pain",
            "im in pain",
            "i fell",
            "i fall",
            "fall down",
            "fell down",
            "ow",
            "oww",
            "owww",
            "ouch",
            "ah",
            "ahh",
            "ahhh",
            "aah",
            "aahh",
            "aahhh",
            "agh",
            "argh",
            "aiyo",
            "aiyah",
        ],
        "zh": [
            "救命",
            "救命啊",
            "求救",
            "帮我",
            "幫我",
            "帮忙",
            "幫忙",
            "帮帮我",
            "幫幫我",
            "需要帮忙",
            "需要幫忙",
            "jiu ming",
            "jiuming",
            "jiu4 ming4",
            "痛",
            "很痛",
            "跌倒",
            "我跌倒",
            "摔倒",
            "我摔倒",
            "叫救护车",
            "叫救護車",
            "救护车",
            "救護車",
            "啊",
            "哎哟",
            "哎喲",
            "啊",
            "啊痛",
            "好痛",
        ],
        "ms": [
            "tolong",
            "tolong saya",
            "sakit",
            "sakit sangat",
            "jatuh",
            "saya jatuh",
            "ambulans",
            "panggil ambulans",
            "kecemasan",
            "aduh",
            "alamak",
            "bantu",
        ],
        "ta": [
            "help",
            "udavi",
            "uthavi",
            "kaapathu",
            "vali",
            "romba vali",
            "vizhunduten",
            "vizhundhu",
            "ambulance",
            "ayyo",
            "amma",
        ],
    }

    okay_words_by_language = {
        "en": [
            "i am okay",
            "i'm okay",
            "im okay",
            "i okay",
            "i am fine",
            "i'm fine",
            "im fine",
            "okay",
            "ok",
            "fine",
            "no need",
        ],
        "zh": [
            "没事",
            "我没事",
            "我沒事",
            "不用",
            "不用帮忙",
            "不用幫忙",
            "还好",
            "我还好",
            "我還好",
            "还可以",
            "還可以",
        ],
        "ms": [
            "saya okay",
            "saya ok",
            "tak apa",
            "tidak apa",
            "tak perlu",
            "saya baik",
        ],
        "ta": [
            "naan okay",
            "naan ok",
            "seri",
            "paravala",
            "vendam",
        ],
    }

    help_words = list(help_words_by_language.get(language, help_words_by_language["en"]))
    okay_words = list(okay_words_by_language.get(language, okay_words_by_language["en"]))

    # Keep English fallback for all languages because some users may still shout "help".
    if language != "en":
        help_words += help_words_by_language["en"]
        okay_words += okay_words_by_language["en"]

    # Help phrases first, so "help I am okay" still becomes help.
    for word in help_words:
        if contains_phrase(text, word):
            return "help"

    for word in okay_words:
        if contains_phrase(text, word):
            return "ok"

    if transcript:
        return "unclear"

    if voice_level > VOICE_THRESHOLD:
        return "unclear"

    return "no_response"


def check_response(preferred_language):
    print("\n===== VOICE CHECK-IN =====")

    # Fresh pause check immediately before the first "EchoSync check-in..." line.
    # This fixes the issue where the caregiver pauses the node but the first
    # check-in sentence still plays.
    latest_control_state = get_node_control_state()

    if not latest_control_state.get("sensorMonitoringEnabled", True):
        print("Node is paused by caregiver. EchoSync check-in prompt skipped.")
        lcd_display("NODE PAUSED", "NO CHECK-IN", force=True)
        return False, 0, "", "paused"

    preferred_language = normalize_language(
        latest_control_state.get("preferredLanguage", preferred_language)
    )

    lcd_display("CHECK-IN", "LISTENING", force=True)

    prompt = get_checkin_prompt(preferred_language)

    print("Preferred check-in language:", prompt["label"])

    checkin_played = speak(
        prompt["text"],
        voice=prompt["voice"],
        lang=prompt["lang"],
        stop_if_node_paused=True,
    )

    if not checkin_played:
        print("EchoSync check-in prompt was stopped/skipped because the node was paused.")
        lcd_display("NODE PAUSED", "NO CHECK-IN", force=True)
        return False, 0, "", "paused"

    if is_node_paused_for_speech():
        print("Node paused after check-in prompt. Mic recording skipped.")
        lcd_display("NODE PAUSED", "NO RECORD", force=True)
        return False, 0, "", "paused"

    record_audio(5)

    if is_node_paused_for_speech():
        print("Node paused during/after mic recording. STT and escalation skipped.")
        lcd_display("NODE PAUSED", "NO ESCALATE", force=True)
        return False, 0, "", "paused"

    level = get_voice_level()
    print("Mic voice level:", level)

    transcript = transcribe_audio(preferred_language)
    print("Transcript:", transcript)

    voice_intent = classify_voice_intent(transcript, level, preferred_language)
    print("Voice intent:", voice_intent)

    responded = voice_intent in ["help", "ok", "unclear"]

    lcd_display("CHECK-IN", f"VOICE:{voice_intent}", force=True)

    return responded, level, transcript, voice_intent


def listen_for_direct_help(preferred_language):
    print("\n===== DIRECT HELP LISTEN =====")

    language = normalize_language(preferred_language)
    lcd_line1, lcd_line2 = get_direct_help_lcd_prompt(language)

    print("Direct help preferred language:", language)
    print("Direct help Azure STT language:", get_stt_language(language))
    lcd_display(lcd_line1, lcd_line2, force=True)

    record_audio(HELP_RECORD_SECONDS)

    level = get_voice_level()
    print("Direct help mic level:", level)

    if level < HELP_VOICE_RMS_THRESHOLD:
        print("Direct help: voice level too low")
        lcd_display(lcd_line1, "NO SPEECH", force=True)
        return False, level, "", "no_response"

    transcript = transcribe_audio(language)
    print("Direct help transcript:", transcript)

    voice_intent = classify_voice_intent(transcript, level, language)
    print("Direct help intent:", voice_intent)

    direct_help_triggered = False

    if voice_intent == "help":
        direct_help_triggered = True

    # STRICT DIRECT-HELP FIX:
    # Do NOT convert every loud unclear sentence into a help request.
    # Example false trigger: Azure heard "Review one connection review item"
    # and mic level was above PAIN_SOUND_VOICE_THRESHOLD, so the old code
    # treated it as "help" even though the transcript had no help/pain word.
    #
    # Now, direct-help only starts when classify_voice_intent() actually finds
    # help / ow / ah / ouch / 救命 / tolong / sakit / etc.
    elif voice_intent == "unclear" and level >= PAIN_SOUND_VOICE_THRESHOLD:
        print(
            "Direct help: loud unclear speech detected, "
            "but no help/pain word found. No direct-help trigger."
        )
        lcd_display("UNCLEAR SPEECH", "NO HELP WORD", force=True)
        return False, level, transcript, "unclear"

    if direct_help_triggered:
        lcd_display("DIRECT HELP", "HEARD ONCE", force=True)

        # Give the acknowledgement sound immediately, in the node preferred language.
        # This happens once when direct-help is first detected.
        direct_help_ack = get_direct_help_ack_prompt(language)
        speak(
            direct_help_ack["text"],
            voice=direct_help_ack["voice"],
            lang=direct_help_ack["lang"],
            stop_if_node_paused=True,
        )

        lcd_display("DIRECT HELP", "CHECK-IN", force=True)
        return True, level, transcript, "help"

    lcd_display(lcd_line1, "NO HELP WORD", force=True)
    return False, level, transcript, voice_intent

# ==========================
# Risk Logic
# ==========================

def should_start_voice_check(sensor_data):
    possible_fall = safe_int(sensor_data.get("possibleFall", 0))
    return possible_fall == 1


def should_skip_direct_help_listener(sensor_data):
    """
    Direct-help voice recording blocks the loop for HELP_RECORD_SECONDS.
    During a possible fall pattern, keep reading Arduino lines instead so
    load-first and sound-first combinations are not missed or delayed.
    """
    if not SKIP_DIRECT_HELP_DURING_SENSOR_ACTIVITY:
        return False

    sensor_activity = (
        safe_int(sensor_data.get("rawSoundDetected", 0)) == 1
        or safe_int(sensor_data.get("soundDetected", 0)) == 1
        or safe_int(sensor_data.get("freshSoundForFall", 0)) == 1
        or safe_int(sensor_data.get("recentSoundForLoad", 0)) == 1
        or safe_int(sensor_data.get("loadSuddenChange", 0)) == 1
        or safe_int(sensor_data.get("recentLoadForSound", 0)) == 1
        or safe_int(sensor_data.get("distanceJump", 0)) == 1
        or safe_int(sensor_data.get("loadChange", 0)) >= int(LOAD_SUDDEN_DELTA * 0.5)
    )

    return sensor_activity


def should_send_low_risk_demo_alert(sensor_data, now):
    """
    Demo-only Low confidence trigger using real Arduino sensor readings.

    It triggers when the node has a stable low-risk condition:
    - no direct help word
    - no possible fall
    - no fresh fall sound
    - no sudden load-cell pressure change
    - no ultrasonic distance jump

    This allows the SCDF dashboard to show a Low confidence card during demo,
    without affecting the existing Medium/High/Critical paths.
    """
    global low_risk_candidate_since, last_low_risk_demo_time

    if not LOW_RISK_DEMO_ALERTS:
        return False

    if now - last_low_risk_demo_time < LOW_RISK_DEMO_COOLDOWN:
        return False

    possible_fall = safe_int(sensor_data.get("possibleFall", 0))
    direct_help_request = safe_int(sensor_data.get("directHelpRequest", 0))
    fresh_sound_for_fall = safe_int(sensor_data.get("freshSoundForFall", 0))
    load_sudden_change = safe_int(sensor_data.get("loadSuddenChange", 0))
    distance_jump = safe_int(sensor_data.get("distanceJump", 0))
    bed_fall_likely = safe_int(sensor_data.get("bedFallLikely", 0))
    ground_fall_likely = safe_int(sensor_data.get("groundFallLikely", 0))
    ground_fall_strong = safe_int(sensor_data.get("groundFallStrong", 0))
    clap_likely = safe_int(sensor_data.get("clapLikely", 0))

    emergency_evidence = (
        possible_fall == 1
        or direct_help_request == 1
        or fresh_sound_for_fall == 1
        or load_sudden_change == 1
        or distance_jump == 1
        or bed_fall_likely == 1
        or ground_fall_likely == 1
        or ground_fall_strong == 1
        or clap_likely == 1
    )

    if emergency_evidence:
        low_risk_candidate_since = None
        return False

    near_detected = safe_int(sensor_data.get("nearDetected", 0))

    # Low demo can be triggered by either:
    # 1) stable object/person near ultrasonic sensor, OR
    # 2) stable normal monitoring if LOW_RISK_ALLOW_NORMAL_STABLE is True.
    low_risk_candidate = near_detected == 1 or LOW_RISK_ALLOW_NORMAL_STABLE

    if not low_risk_candidate:
        low_risk_candidate_since = None
        return False

    if low_risk_candidate_since is None:
        low_risk_candidate_since = now
        print("Low-risk demo candidate detected. Hold sensors steady...")
        return False

    if now - low_risk_candidate_since < LOW_RISK_STABLE_SECONDS:
        return False

    last_low_risk_demo_time = now
    low_risk_candidate_since = None
    return True


def calculate_risk(sensor_data, responded, voice_intent):
    alert = safe_int(sensor_data.get("alert", 0))
    possible_fall = safe_int(sensor_data.get("possibleFall", 0))
    direct_help_request = safe_int(sensor_data.get("directHelpRequest", 0))
    low_risk_demo_alert = safe_int(sensor_data.get("lowRiskDemoAlert", 0))

    if low_risk_demo_alert == 1:
        # Low-risk confidence is still based on real sensor evidence,
        # but capped inside the low-risk range so it does not look like Medium/High.
        near_detected = safe_int(sensor_data.get("nearDetected", 0))
        pir_motion = safe_int(sensor_data.get("pirMotion", 0))
        load_ready = safe_int(sensor_data.get("loadReady", 0))
        load_detected = safe_int(sensor_data.get("loadDetected", 0))
        load_change = safe_int(sensor_data.get("loadChange", 0))
        distance_change = safe_int(sensor_data.get("distanceChange", 0))
        sound_level = safe_int(sensor_data.get("soundLevel", 0))
        sound_baseline = safe_int(sensor_data.get("soundBaseline", 0))

        confidence = 40
        reasons = ["Low-risk stable monitoring detected"]

        if pir_motion == 1:
            confidence += 3
            reasons.append("motion was present but no fall pattern was found")

        if near_detected == 1:
            confidence += 6
            reasons.append("ultrasonic proximity was detected")

        if load_ready == 1 and load_detected == 1:
            confidence += 5
            reasons.append("load cell detected pressure but no sudden pressure change")

        elif load_change > 100:
            confidence += 3
            reasons.append("minor load cell change was detected")

        if distance_change > 0:
            confidence += min(3, distance_change)
            reasons.append("minor ultrasonic distance change was detected")

        if sound_level > sound_baseline + 1:
            confidence += 2
            reasons.append("slightly raised sound level was detected")

        # Keep demo Low alerts inside the low-confidence range.
        confidence = min(confidence, 52)

        return "Low", confidence, "; ".join(reasons)

    load_ready = safe_int(sensor_data.get("loadReady", 0))
    load_detected = safe_int(sensor_data.get("loadDetected", 0))
    load_sudden_change = safe_int(sensor_data.get("loadSuddenChange", 0))

    bed_fall_likely = safe_int(sensor_data.get("bedFallLikely", 0))
    ground_fall_likely = safe_int(sensor_data.get("groundFallLikely", 0))
    ground_fall_strong = safe_int(sensor_data.get("groundFallStrong", 0))

    if direct_help_request == 1 and voice_intent == "ok":
        return "Low", 45, "Resident initially called help but confirmed they are okay after EchoSync check-in"

    if direct_help_request == 1 and voice_intent == "help":
        return "Critical", 98, "Resident repeated help request after EchoSync check-in"

    if direct_help_request == 1 and voice_intent == "unclear":
        return "Medium", 70, "Resident called help but response was unclear after EchoSync check-in; caregiver verification needed"

    if direct_help_request == 1 and not responded:
        return "High", 90, "Resident called help but gave no response after EchoSync check-in"

    if voice_intent == "help":
        return "Critical", 98, "Resident verbally requested help"

    if voice_intent == "ok":
        return "Low", 45, "Resident said they are okay after voice check-in"

    if voice_intent == "unclear" and possible_fall == 1:
        return "Medium", 70, "Unclear resident response after possible fall; caregiver verification needed"

    if ground_fall_strong == 1 and not responded:
        return "Critical", 96, "Possible ground fall pattern with no resident response"

    if ground_fall_likely == 1 and not responded:
        return "High", 90, "Possible ground fall detected using fresh sound and ultrasonic distance change"

    if bed_fall_likely == 1 and not responded:
        return "Critical", 95, "Possible bed fall pattern with no resident response"

    if possible_fall == 1 and not responded:
        return "Critical", 95, "Possible fall pattern with no resident response"

    if load_ready == 1 and load_sudden_change == 1 and not responded:
        return "High", 90, "Sudden load cell pressure change detected with no resident response"

    if alert == 1 and not responded:
        return "High", 88, "Sensor alert with no resident response"

    if alert == 1 and responded:
        return "Medium", 70, "Sensor alert received a response, but caregiver verification is still recommended"

    if load_ready == 1 and load_detected == 1:
        return "Low", 45, "Low-risk pressure monitoring event"

    return "Low", 40, "Low-risk monitoring event"


def get_event_type(risk_level, sensor_data, voice_intent):
    direct_help_request = safe_int(sensor_data.get("directHelpRequest", 0))
    low_risk_demo_alert = safe_int(sensor_data.get("lowRiskDemoAlert", 0))

    if low_risk_demo_alert == 1:
        near_detected = safe_int(sensor_data.get("nearDetected", 0))

        if near_detected == 1:
            return "Low-risk Proximity Check"

        return "Low-risk Monitoring Check"

    sleeping_likely = safe_int(sensor_data.get("sleepingLikely", 0))
    clap_likely = safe_int(sensor_data.get("clapLikely", 0))
    possible_fall = safe_int(sensor_data.get("possibleFall", 0))
    bed_fall_likely = safe_int(sensor_data.get("bedFallLikely", 0))
    ground_fall_likely = safe_int(sensor_data.get("groundFallLikely", 0))
    load_sudden_change = safe_int(sensor_data.get("loadSuddenChange", 0))

    # Direct-help cases should not all show the same dashboard card title.
    if direct_help_request == 1:
        if voice_intent == "help":
            return "Repeated Help Request"
        if voice_intent == "ok":
            return "Resident Verified After Help"
        if voice_intent == "unclear":
            return "Unclear Help Response"
        if voice_intent == "paused":
            return "Node Paused / Check-in Skipped"
        return "Help Call / No Response"

    if voice_intent == "help":
        return "Verbal Help Request"

    if voice_intent == "ok":
        return "Resident Verified Okay"

    if voice_intent == "unclear":
        return "Unclear Voice Response"

    if voice_intent == "paused":
        return "Node Paused / Check-in Skipped"

    if sleeping_likely == 1:
        return "Resting / Sleeping Pattern"

    if clap_likely == 1:
        return "Sound Only / Clap Pattern"

    if risk_level in ["High", "Critical"] and ground_fall_likely == 1:
        return "Possible Ground Fall"

    if risk_level in ["High", "Critical"] and bed_fall_likely == 1:
        return "Possible Bed Fall"

    if risk_level in ["High", "Critical"] and possible_fall == 1:
        return "Possible Fall / No Response"

    if risk_level in ["High", "Critical"] and load_sudden_change == 1:
        return "Sudden Pressure Change"

    if risk_level in ["High", "Critical"]:
        return "Emergency Review Needed"

    if risk_level == "Medium":
        return "Caregiver Verification Needed"

    return "Low-risk Monitoring Event"


# ==========================
# Node Control
# ==========================

def get_node_control_state():
    """
    Load node-control from personal laptop, Dell laptop and OpenShift.

    Safe merge rule:
    - sensorMonitoringEnabled: if ANY device pauses/turns monitoring off, Pi pauses.
    - pauseLowRiskMonitoring: if ANY device pauses low-risk monitoring, Pi pauses low-risk.
    - preferredLanguage: use the most recently updated API state when timestamp exists.
      If no timestamp exists, use the first non-default language found.

    Fast demo rule:
    - Fetch all control URLs in parallel, not one-by-one.
    """
    loaded_controls = []

    def fetch_control(url):
        try:
            response = requests.get(url, timeout=NODE_CONTROL_FULL_TIMEOUT)

            if response.status_code != 200:
                return url, None, f"status {response.status_code}"

            return url, response.json(), None

        except Exception as e:
            return url, None, str(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=HTTP_WORKERS) as executor:
        futures = [executor.submit(fetch_control, url) for url in NODE_CONTROL_APIS]

        for future in concurrent.futures.as_completed(futures):
            url, data, error = future.result()

            if data is None:
                print("Node control not available from:", url, "-", error)
                continue

            loaded_controls.append((url, data))
            print("Node control loaded from:", url)

    if not loaded_controls:
        return {
            "pauseLowRiskMonitoring": False,
            "sensorMonitoringEnabled": True,
            "reason": None,
            "preferredLanguage": DEFAULT_LANGUAGE,
        }

    sensor_monitoring_enabled = True
    pause_low_risk_monitoring = False
    reason = None

    language_candidates_with_time = []
    language_candidates_no_time = []

    for index, (url, data) in enumerate(loaded_controls):
        current_sensor_enabled = safe_bool(
            data.get("sensorMonitoringEnabled", True),
            True,
        )
        current_pause_low_risk = safe_bool(
            data.get("pauseLowRiskMonitoring", False),
            False,
        )

        if not current_sensor_enabled:
            sensor_monitoring_enabled = False
            if not reason:
                reason = data.get("reason") or f"Paused from {url}"

        if current_pause_low_risk:
            pause_low_risk_monitoring = True
            if not reason:
                reason = data.get("reason") or f"Low-risk paused from {url}"

        raw_language = data.get("preferredLanguage", DEFAULT_LANGUAGE)
        language = normalize_language(raw_language)
        timestamp = get_control_timestamp(data)

        if timestamp is not None:
            language_candidates_with_time.append((timestamp, index, language, url))
        else:
            language_candidates_no_time.append((index, language, url))

    selected_language = DEFAULT_LANGUAGE
    language_source = None

    if language_candidates_with_time:
        latest = max(language_candidates_with_time, key=lambda item: (item[0], item[1]))
        selected_language = latest[2]
        language_source = latest[3]

    else:
        # Without timestamps, let any device control language by choosing the first
        # non-default language found across the three APIs. If all are default,
        # use English.
        for _, language, url in language_candidates_no_time:
            if language != DEFAULT_LANGUAGE:
                selected_language = language
                language_source = url
                break

        if language_source is None and language_candidates_no_time:
            selected_language = language_candidates_no_time[0][1]
            language_source = language_candidates_no_time[0][2]

    print(
        "Merged node control:",
        f"sensorMonitoringEnabled={sensor_monitoring_enabled}",
        f"pauseLowRiskMonitoring={pause_low_risk_monitoring}",
        f"preferredLanguage={selected_language}",
        f"languageSource={language_source}",
    )

    return {
        "pauseLowRiskMonitoring": pause_low_risk_monitoring,
        "sensorMonitoringEnabled": sensor_monitoring_enabled,
        "reason": reason,
        "preferredLanguage": selected_language,
    }

# ==========================
# GB10 AI Summary
# ==========================

def ask_gb10(
    sensor_data,
    responded,
    voice_level,
    transcript,
    voice_intent,
    risk_level,
    confidence,
    reason,
    preferred_language,
):
    response_status = (
        "Resident response detected"
        if responded
        else "No resident response detected"
    )

    prompt = f"""
EchoSync sensor alert from a senior living alone in a Singapore HDB flat.

Sensor evidence:
- Event source: {sensor_data.get("eventSource")}
- Direct help request: {sensor_data.get("directHelpRequest")}
- Sound level: {sensor_data.get("soundLevel")}
- Sound baseline: {sensor_data.get("soundBaseline")}
- Raw sound detected: {sensor_data.get("rawSoundDetected")}
- Sound detected: {sensor_data.get("soundDetected")}
- Fresh sound for fall: {sensor_data.get("freshSoundForFall")}
- Microphone digital trigger: {sensor_data.get("micDigital")}
- PIR motion: {sensor_data.get("pirMotion")}
- PIR motion stopped: {sensor_data.get("pirMotionStopped")}
- Ultrasonic distance: {sensor_data.get("distanceCm")} cm
- Near object detected: {sensor_data.get("nearDetected")}
- Ultrasonic distance change: {sensor_data.get("distanceChange")}
- Ultrasonic distance jump: {sensor_data.get("distanceJump")}
- Load cell ready: {sensor_data.get("loadReady")}
- Load cell raw value: {sensor_data.get("loadRaw")}
- Load cell net value: {sensor_data.get("loadNet")}
- Load cell pressure detected: {sensor_data.get("loadDetected")}
- Load cell net change: {sensor_data.get("loadChange")}
- Load cell sudden change: {sensor_data.get("loadSuddenChange")}
- Load + sound combo within {LOAD_SOUND_PAIR_WINDOW}s: {sensor_data.get("loadSoundCombo")}
- Sleeping/resting pattern likely: {sensor_data.get("sleepingLikely")}
- Clap/noise-only pattern likely: {sensor_data.get("clapLikely")}
- Bed fall pattern likely: {sensor_data.get("bedFallLikely")}
- Ground/floor fall pattern likely: {sensor_data.get("groundFallLikely")}
- Strong ground/floor fall pattern: {sensor_data.get("groundFallStrong")}
- Possible fall flag: {sensor_data.get("possibleFall")}
- Alert flag: {sensor_data.get("alert")}
- Low-risk demo alert: {sensor_data.get("lowRiskDemoAlert")}

Voice check-in:
- Preferred language: {preferred_language}
- {response_status}
- Mic voice level: {voice_level}
- Transcript: {transcript}
- Voice intent: {voice_intent}

Risk assessment:
- Risk level: {risk_level}
- Confidence: {confidence}%
- Reason: {reason}

Explain this alert for an emergency operator, myResponder operator, or caregiver.
Keep it short, safe, and do not diagnose.
If the resident repeatedly requested help or gave no response, state that operator review is needed.
If the resident said they are okay, state that the alert is low risk and caregiver monitoring is recommended.
If the resident response is unclear, state that caregiver verification is recommended.
If lowRiskDemoAlert is 1, explain it as a low-risk monitoring/proximity check and do not describe it as a fall.
Only mention a sudden pressure change if loadSuddenChange is 1.
Only mention a possible fall if possibleFall is 1.
"""

    payload = {
        "model": GB10_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are EchoSync, an AI-assisted pre-arrival intelligence system. "
                    "Explain sensor evidence clearly and safely. "
                    "Do not claim medical diagnosis."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.2,
        "max_tokens": 180,
    }

    try:
        response = requests.post(
            GB10_URL,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer local",
            },
            json=payload,
            timeout=GB10_TIMEOUT,
        )

        response.raise_for_status()
        result = response.json()

        return result["choices"][0]["message"]["content"]

    except Exception as e:
        return f"AI summary unavailable: {e}"


# ==========================
# Dashboard / Caregiver Send
# ==========================

def build_payload(
    sensor_data,
    responded,
    voice_level,
    transcript,
    voice_intent,
    ai_summary,
    risk_level,
    confidence,
    reason,
    preferred_language,
):
    return {
        "nodeId": "NODE-HDB-302-08-112",
        "resident": "Mdm Tan Siew Lan",
        "location": "Blk 302 Ang Mo Kio Ave 3, #08-112",
        "eventType": get_event_type(risk_level, sensor_data, voice_intent),
        "riskLevel": risk_level,
        "confidence": confidence,
        "reason": reason,
        "sensorData": sensor_data,
        "voiceCheckIn": {
            "preferredLanguage": preferred_language,
            "responded": responded,
            "voiceLevel": voice_level,
            "transcript": transcript,
            "intent": voice_intent,
        },
        "aiSummary": ai_summary,
        "source": "Raspberry Pi + Arduino + Load Cell + Azure Voice/STT + GB10",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def post_json(url, payload, label):
    try:
        response = requests.post(url, json=payload, timeout=ALERT_POST_TIMEOUT)

        print(f"{label} URL:", url)
        print(f"{label} status:", response.status_code)
        print(f"{label} reply:", response.text)

    except Exception as e:
        print(f"{label} send error to {url}:", e)


def post_json_to_many(urls, payload, label):
    # Send to all dashboards in parallel so one slow/unreachable laptop does not
    # delay the rest of the alert flow.
    with concurrent.futures.ThreadPoolExecutor(max_workers=HTTP_WORKERS) as executor:
        futures = []

        for index, url in enumerate(urls, start=1):
            futures.append(executor.submit(post_json, url, payload, f"{label} #{index}"))

        for future in concurrent.futures.as_completed(futures):
            future.result()


def send_to_dashboard(payload):
    post_json_to_many(DASHBOARD_APIS, payload, "Dashboard")


def send_to_caregiver(payload):
    post_json_to_many(CAREGIVER_APIS, payload, "Caregiver app")


def send_to_myresponder(payload):
    post_json_to_many(MYRESPONDER_APIS, payload, "myResponder")

# ==========================
# Logging
# ==========================

def log_alert(
    sensor_data,
    responded,
    voice_level,
    transcript,
    voice_intent,
    risk_level,
    confidence,
    preferred_language,
):
    try:
        with open("echosync_log.txt", "a") as f:
            f.write(
                f"{time.ctime()} | "
                f"EventSource={sensor_data.get('eventSource')} | "
                f"DirectHelpRequest={sensor_data.get('directHelpRequest')} | "
                f"Alert={sensor_data.get('alert')} | "
                f"PossibleFall={sensor_data.get('possibleFall')} | "
                f"SoundLevel={sensor_data.get('soundLevel')} | "
                f"RawSoundDetected={sensor_data.get('rawSoundDetected')} | "
                f"SoundDetected={sensor_data.get('soundDetected')} | "
                f"FreshSoundForFall={sensor_data.get('freshSoundForFall')} | "
                f"DistanceCm={sensor_data.get('distanceCm')} | "
                f"DistanceChange={sensor_data.get('distanceChange')} | "
                f"DistanceJump={sensor_data.get('distanceJump')} | "
                f"LoadDetected={sensor_data.get('loadDetected')} | "
                f"LoadSuddenChange={sensor_data.get('loadSuddenChange')} | "
                f"LoadSoundCombo={sensor_data.get('loadSoundCombo')} | "
                f"SleepingLikely={sensor_data.get('sleepingLikely')} | "
                f"ClapLikely={sensor_data.get('clapLikely')} | "
                f"BedFallLikely={sensor_data.get('bedFallLikely')} | "
                f"GroundFallLikely={sensor_data.get('groundFallLikely')} | "
                f"GroundFallStrong={sensor_data.get('groundFallStrong')} | "
                f"PreferredLanguage={preferred_language} | "
                f"Transcript={transcript} | "
                f"Intent={voice_intent} | "
                f"Risk={risk_level} | "
                f"Confidence={confidence} | "
                f"Responded={responded} | "
                f"Voice={voice_level}\n"
            )

    except Exception as e:
        print("Log error:", e)


# ==========================
# Main Loop
# ==========================

try:
    while True:
        line = ser.readline().decode(errors="ignore").strip()

        if not line:
            continue

        print("Arduino:", line)

        if not line.startswith("{"):
            continue

        try:
            sensor_data = json.loads(line)
        except json.JSONDecodeError:
            print("Invalid JSON received")
            continue

        sensor_data = enrich_sensor_data(sensor_data)

        print_sensor_screen(sensor_data)

        lcd_line1, lcd_line2 = get_test_case_lcd(sensor_data)
        lcd_display(lcd_line1, lcd_line2)

        now = time.time()

        possible_fall_now = should_start_voice_check(sensor_data)

        direct_help_detected = False
        direct_help_level = 0
        direct_help_transcript = ""
        direct_help_intent = "no_response"

        if not possible_fall_now:
            if fall_normal_since is None:
                fall_normal_since = now

            if fall_latched and now - fall_normal_since >= FALL_REARM_SECONDS:
                print("Fall sensor returned to normal. EchoSync is re-armed.")
                fall_latched = False
                lcd_display("RE-ARMED", "MONITORING", force=True)

            if safe_int(sensor_data.get("sleepingLikely", 0)) == 1:
                print("No alert: resting/sleeping pattern detected.")

            elif safe_int(sensor_data.get("clapLikely", 0)) == 1:
                print("No alert: clap/noise-only pattern detected.")

            else:
                print("No alert: normal monitoring.")

            if should_send_low_risk_demo_alert(sensor_data, now):
                near_detected = safe_int(sensor_data.get("nearDetected", 0))

                print("Low-risk demo sensor condition detected. Sending to GB10/dashboard for confidence testing.")

                sensor_data["lowRiskDemoAlert"] = 1
                sensor_data["alert"] = 1

                if near_detected == 1:
                    sensor_data["eventSource"] = "Low-risk ultrasonic proximity detected; no fall pattern found"
                    lcd_display("LOW RISK", "PROXIMITY", force=True)
                else:
                    sensor_data["eventSource"] = "Low-risk stable monitoring detected; no fall pattern found"
                    lcd_display("LOW RISK", "GB10 TEST", force=True)

                possible_fall_now = True

            if not possible_fall_now and direct_help_latched and now - direct_help_latched_time < DIRECT_HELP_REARM_SECONDS:
                print("Direct help already detected once. Waiting before re-arming direct-help listener.")
                lcd_display("HELP HEARD", "WAIT CHECK-IN", force=True)
                continue

            if not possible_fall_now and direct_help_latched and now - direct_help_latched_time >= DIRECT_HELP_REARM_SECONDS:
                print("Direct help listener re-armed.")
                direct_help_latched = False

            if not possible_fall_now and should_skip_direct_help_listener(sensor_data):
                print("Direct-help mic skipped: recent sensor activity, keeping load/sound detection responsive.")
                lcd_display("SENSOR ACTIVE", "NO MIC BLOCK", force=True)
                continue

            if not possible_fall_now and DIRECT_HELP_LISTENING and now - last_help_listen_time >= HELP_LISTEN_INTERVAL:
                last_help_listen_time = now

                control_state = get_node_control_state()

                if not control_state.get("sensorMonitoringEnabled", True):
                    print("Node is paused by caregiver. Direct-help listener skipped.")
                    lcd_display("NODE PAUSED", "NO LISTEN", force=True)
                    continue

                preferred_language = normalize_language(
                    control_state.get("preferredLanguage", DEFAULT_LANGUAGE)
                )

                direct_help_detected, direct_help_level, direct_help_transcript, direct_help_intent = listen_for_direct_help(
                    preferred_language
                )

                if direct_help_detected:
                    print("Direct help word detected once. Starting EchoSync check-in flow.")

                    direct_help_latched = True
                    direct_help_latched_time = now

                    sensor_data["directHelpRequest"] = 1
                    sensor_data["possibleFall"] = 1
                    sensor_data["alert"] = 1
                    sensor_data["eventSource"] = "Direct help word heard once; check-in required"
                    sensor_data["directHelpTranscript"] = direct_help_transcript
                    sensor_data["directHelpVoiceLevel"] = direct_help_level
                    sensor_data["directHelpLanguage"] = preferred_language

                    lcd_display("TC12 HELP", "CHECK-IN", force=True)

                    possible_fall_now = True
                else:
                    continue
            else:
                if not possible_fall_now:
                    continue

        fall_normal_since = None

        if fall_latched:
            print("Fall condition still active. Ignoring repeat trigger until sensors return to normal.")
            lcd_display("FALL LATCHED", "WAIT NORMAL", force=True)
            continue

        if now - last_alert_time <= ALERT_COOLDOWN:
            print("Fall/help detected, but alert cooldown is still active.")
            lcd_display("COOLDOWN", "WAIT", force=True)
            continue

        fall_latched = True

        print("\n===== ECHOSYNC ALERT =====")
        print("Event source:", sensor_data.get("eventSource"))
        print("Direct help request:", sensor_data.get("directHelpRequest", 0))
        print("Sound level:", sensor_data.get("soundLevel", 0))
        print("Raw sound detected:", sensor_data.get("rawSoundDetected", 0))
        print("Sound detected:", sensor_data.get("soundDetected", 0))
        print("Fresh sound for fall:", sensor_data.get("freshSoundForFall", 0))
        print("Distance:", sensor_data.get("distanceCm", -1))
        print("Distance change:", sensor_data.get("distanceChange", 0))
        print("Distance jump:", sensor_data.get("distanceJump", 0))
        print("Load detected:", sensor_data.get("loadDetected", 0))
        print("Sleeping likely:", sensor_data.get("sleepingLikely", 0))
        print("Clap likely:", sensor_data.get("clapLikely", 0))
        print("Bed fall likely:", sensor_data.get("bedFallLikely", 0))
        print("Ground fall likely:", sensor_data.get("groundFallLikely", 0))
        print("Possible fall:", sensor_data.get("possibleFall", 0))

        lcd_display("ECHOSYNC ALERT", "CHECK-IN", force=True)

        control_state = get_node_control_state()

        sensor_monitoring_enabled = control_state.get("sensorMonitoringEnabled", True)
        pause_low_risk = control_state.get("pauseLowRiskMonitoring", False)
        preferred_language = normalize_language(
            control_state.get("preferredLanguage", DEFAULT_LANGUAGE)
        )

        print("Sensor monitoring enabled:", sensor_monitoring_enabled)
        print("Pause low-risk monitoring:", pause_low_risk)
        print("Preferred language from app/node control:", preferred_language)

        if not sensor_monitoring_enabled:
            print("Away Mode / node pause is ON.")
            print("Node stays online, but sensor alerts, voice check-in, mic recording, GB10 and escalation are paused.")
            lcd_display("NODE PAUSED", "ALERT PAUSED", force=True)
            fall_latched = False
            last_alert_time = now
            continue

        if safe_int(sensor_data.get("lowRiskDemoAlert", 0)) == 1:
            print("Low-risk demo alert. Skipping voice check-in and sending sensor evidence to GB10.")
            responded = False
            voice_level = 0
            transcript = ""
            voice_intent = "not_required"

        elif safe_int(sensor_data.get("directHelpRequest", 0)) == 1:
            print("Direct help heard once. Acknowledgement already played. Running check-in before deciding escalation.")

            responded, voice_level, transcript, voice_intent = check_response(preferred_language)

        else:
            responded, voice_level, transcript, voice_intent = check_response(preferred_language)

        if voice_intent == "paused":
            print("Check-in paused by caregiver. Alert will not be sent.")
            lcd_display("NODE PAUSED", "NO SEND", force=True)
            fall_latched = False
            last_alert_time = now
            continue

        print("Resident response:", "DETECTED" if responded else "NO RESPONSE")
        print("Transcript:", transcript)
        print("Voice intent:", voice_intent)

        if safe_int(sensor_data.get("lowRiskDemoAlert", 0)) == 1:
            print("Low-risk demo alert. No resident voice prompt needed.")
        else:
            response_prompt = get_response_prompt(preferred_language, voice_intent)
            response_prompt_played = speak(
                response_prompt["text"],
                voice=response_prompt["voice"],
                lang=response_prompt["lang"],
                stop_if_node_paused=True,
            )

            if not response_prompt_played:
                print("Response prompt stopped/skipped because caregiver paused the node. Alert will not be sent.")
                lcd_display("NODE PAUSED", "NO SEND", force=True)
                fall_latched = False
                last_alert_time = now
                continue

        risk_level, confidence, reason = calculate_risk(
            sensor_data,
            responded,
            voice_intent,
        )

        print("Risk level:", risk_level)
        print("Confidence:", confidence)
        print("Reason:", reason)

        if risk_level in ["High", "Critical"]:
            lcd_display(risk_level.upper(), "DASHBOARD", force=True)
        elif risk_level == "Medium":
            lcd_display("MEDIUM", "CAREGIVER", force=True)
        else:
            lcd_display("LOW", "CAREGIVER", force=True)

        log_alert(
            sensor_data,
            responded,
            voice_level,
            transcript,
            voice_intent,
            risk_level,
            confidence,
            preferred_language,
        )

        print("\nSending to GB10...")

        ai_summary = ask_gb10(
            sensor_data,
            responded,
            voice_level,
            transcript,
            voice_intent,
            risk_level,
            confidence,
            reason,
            preferred_language,
        )

        print("\n===== GB10 AI SUMMARY =====")
        print(ai_summary)
        print("===========================\n")

        payload = build_payload(
            sensor_data,
            responded,
            voice_level,
            transcript,
            voice_intent,
            ai_summary,
            risk_level,
            confidence,
            reason,
            preferred_language,
        )

        if risk_level in ["High", "Critical"]:
            print("Routing: HIGH/CRITICAL → SCDF dashboard / emergency operator review")
            send_to_dashboard(payload)

        elif risk_level in ["Low", "Medium"]:
            if safe_int(sensor_data.get("lowRiskDemoAlert", 0)) == 1:
                print("Routing: DEMO LOW → caregiver app + SCDF dashboard for confidence testing")
                send_to_caregiver(payload)
                send_to_dashboard(payload)

            elif pause_low_risk and risk_level == "Low":
                print("Routing: LOW alert paused by caregiver setting")
                print("Medium, High, Critical and no-response alerts remain active.")
                lcd_display("LOW PAUSED", "NO SEND", force=True)
            else:
                print("Routing: LOW/MEDIUM → caregiver app only")
                send_to_caregiver(payload)

        last_alert_time = now

except KeyboardInterrupt:
    pass

except Exception as e:
    print("Error:", e)
    try:
        lcd_display("PY ERROR", "CHECK TERMINAL", force=True)
    except Exception:
        pass
    time.sleep(1)

finally:
    cleanup_and_exit()
