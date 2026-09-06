"""
RehabStroke AI - Flask Backend
Sistem Monitoring Rehabilitasi Pasca-Stroke Berbasis IoT & Machine Learning
Adaptasi dari Streamlit ke Flask + MQTT
v3.0 - Logika on_message diperbaiki sesuai Streamlit asli
"""

from flask import Flask, jsonify, render_template, send_file, request
import paho.mqtt.client as mqtt
import pandas as pd
import numpy as np
import joblib
import os
import threading
import time
from datetime import datetime
from collections import deque

# ==========================================
# 1. INISIALISASI FLASK APP
# ==========================================
app = Flask(__name__)

# ==========================================
# 2. KONFIGURASI GLOBAL
# ==========================================
MQTT_BROKER     = "broker.emqx.io"
MQTT_TOPIC      = "skripsi/ilmi/sensor"
LOG_FILE_PATH   = "logs/log_latihan_arat.csv"
BUFFER_SIZE     = 50
WINDOW_SIZE     = 20
SLIDE_STEP      = 10
RECONNECT_DELAY = 5

GERAKAN_LIST = [
    "hand_to_mouth",
    "hand_to_tophead",
    "hand_to_backhead",
    "cup",
    "big_tube",
    "small_tube",
    "ring"
]

MODEL_FILENAME = {
    "hand_to_mouth"    : "models/model_hand_to_mouth.pkl",
    "hand_to_tophead"  : "models/model_hand_to_tophead.pkl",
    "hand_to_backhead" : "models/model_hand_to_backhead.pkl",
    "cup"              : "models/model_cup.pkl",
    "big_tube"         : "models/model_big_tube.pkl",
    "small_tube"       : "models/model_small_tube.pkl",
    "ring"             : "models/model_ring.pkl",
}

SKOR_LABEL = {
    3: "Gerakan Sempurna",
    2: "Gerakan Terjadi Namun Lambat",
    1: "Gerakan Sangat Terbatas",
    0: "Tidak Ada Gerakan"
}

# ==========================================
# 3. STATE APLIKASI (Thread-Safe)
# ==========================================
state_lock = threading.Lock()

app_state = {
    "sensor_buffer"        : deque(maxlen=BUFFER_SIZE),
    "window_buffer"        : [],
    "current_score"        : None,
    "latest_data"          : [0.0] * 12,
    "selected_model"       : "hand_to_mouth",
    "last_logged_score"    : None,
    "score_holding_buffer" : [],
    "mqtt_connected"       : False,
    "mqtt_reconnect_count" : 0,
    "prediction_history"   : deque(maxlen=500),
}

# ==========================================
# 4. LOAD SEMUA MODEL .PKL
# ==========================================
def load_all_models():
    loaded = {}
    for name, path in MODEL_FILENAME.items():
        try:
            loaded[name] = joblib.load(path)
            print(f"[MODEL] ✅ {name} -> loaded")
        except Exception as e:
            loaded[name] = None
            print(f"[MODEL] ❌ {name} -> {e}")
    return loaded

models_dict = load_all_models()

# ==========================================
# 5. FUNGSI TULIS LOG CSV
# ==========================================
def tulis_log_ke_csv(nama_gerakan, skor, df_win):
    try:
        os.makedirs("logs", exist_ok=True)

        mean_vals = df_win.mean().round(3).to_dict()

        row = {
            "Waktu_Uji"        : datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Gerakan_ARAT"     : str(nama_gerakan).upper(),
            "Prediksi_Skor_AI" : int(skor),
        }

        for col, val in mean_vals.items():
            row[f"{col}_mean"] = val

        df_new = pd.DataFrame(row, index=[0])

        if not os.path.exists(LOG_FILE_PATH) or os.path.getsize(LOG_FILE_PATH) == 0:
            df_new.to_csv(LOG_FILE_PATH, index=False, sep=";")
        else:
            df_new.to_csv(LOG_FILE_PATH, mode="a", header=False, index=False, sep=";")

        with state_lock:
            app_state["prediction_history"].appendleft({
                "waktu"     : row["Waktu_Uji"],
                "gerakan"   : row["Gerakan_ARAT"],
                "skor"      : int(skor),
                "keterangan": SKOR_LABEL.get(int(skor), "-")
            })

        print(f"[LOG] ✅ Tercatat: {nama_gerakan.upper()} | Skor {skor} | {SKOR_LABEL.get(int(skor), '-')}")

    except Exception as e:
        print(f"[LOG] ❌ Gagal menulis log: {e}")

# ==========================================
# 6. ENGINE EKSTRAKSI FITUR & PREDIKSI
# ==========================================
COLS_RAW = ['ax1','ay1','az1','gx1','gy1','gz1',
            'ax2','ay2','az2','gx2','gy2','gz2']

def hitung_prediksi(window_data, nama_gerakan):
    model = models_dict.get(nama_gerakan)

    if model is None:
        return None, None

    df_win = pd.DataFrame(window_data, columns=COLS_RAW)

    row_fitur  = []
    cols_fitur = []

    for c in COLS_RAW:
        row_fitur.append(float(df_win[c].mean()))
        row_fitur.append(float(df_win[c].std()) if len(df_win) > 1 else 0.0)
        row_fitur.append(float(df_win[c].max() - df_win[c].min()))

        cols_fitur.extend([
            f"{c}_mean",
            f"{c}_std",
            f"{c}_range"
        ])

    X = pd.DataFrame([row_fitur], columns=cols_fitur)

    hasil = model.predict(X)[0]

    return int(hasil), df_win

# ==========================================
# 7. MQTT CALLBACKS
# ==========================================
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        client.subscribe(MQTT_TOPIC)

        with state_lock:
            app_state["mqtt_connected"]       = True
            app_state["mqtt_reconnect_count"] = 0

        print(f"[MQTT] ✅ Terhubung ke {MQTT_BROKER}, topic: {MQTT_TOPIC}")

    else:
        print(f"[MQTT] ❌ Gagal koneksi, rc={rc}")

def on_disconnect(client, userdata, rc, properties=None, reasonCode=None):
    with state_lock:
        app_state["mqtt_connected"] = False

    print(f"[MQTT] 🔌 Terputus dari broker (rc={rc})")

# ==========================================
# ON_MESSAGE — BAGIAN YANG DIPERBAIKI
# ==========================================
def on_message(client, userdata, msg):
    try:
        # Parsing payload CSV dari ESP32
        clean_payload = msg.payload.decode().strip()
        payload = clean_payload.split(",")

        if len(payload) < 12:
            return

        data_num = [float(v.strip()) for v in payload[:12]]

        with state_lock:
            app_state["sensor_buffer"].append(data_num)
            app_state["window_buffer"].append(data_num)
            app_state["latest_data"] = data_num

            nama_gerakan    = app_state["selected_model"]
            window_buf_copy = list(app_state["window_buffer"])

        # Jalankan prediksi jika window sudah cukup
        if len(window_buf_copy) >= WINDOW_SIZE:
            skor, df_win = hitung_prediksi(window_buf_copy, nama_gerakan)

            # Total gyro digunakan untuk mendeteksi kondisi bergerak / diam
            total_gyro = sum(abs(data_num[i]) for i in [3, 4, 5, 9, 10, 11])

            with state_lock:

                # =====================================================
                # PERBAIKAN UTAMA:
                # Jangan langsung masukkan skor 0 ke buffer final
                # ketika tangan masih bergerak.
                #
                # Tujuannya:
                # - Prediksi realtime tetap berjalan.
                # - Riwayat prediksi tidak mudah tersimpan sebagai 0 palsu.
                # =====================================================
                if total_gyro > 1.5 and skor == 0:
                    # Tangan masih bergerak, tapi model membaca 0.
                    # Tampilkan status "mengukur", tetapi jangan simpan 0
                    # ke score_holding_buffer.
                    app_state["current_score"] = -1

                else:
                    # Jika skor valid terbaca, simpan ke buffer.
                    skor_buffer = skor if skor is not None else 0

                    app_state["current_score"] = skor_buffer
                    app_state["score_holding_buffer"].append(skor_buffer)

                # =====================================================
                # SIMPAN RIWAYAT HANYA SAAT TANGAN SUDAH DIAM
                # =====================================================
                if total_gyro < 0.40:
                    score_check = app_state["score_holding_buffer"]

                    # Minimal harus ada beberapa hasil prediksi dalam 1 sesi gerakan
                    if len(score_check) > 5:

                        # Prioritaskan skor 1, 2, atau 3 jika tersedia.
                        # Ini mencegah angka 0 mendominasi riwayat.
                        skor_valid = [s for s in score_check if s in [1, 2, 3]]

                        if len(skor_valid) > 0:
                            # Ambil skor valid yang paling sering muncul
                            skor_final = max(set(skor_valid), key=skor_valid.count)
                        else:
                            # Kalau memang tidak ada skor valid sama sekali,
                            # baru simpan sebagai skor 0.
                            skor_final = 0

                        # Anti duplikat: catat hanya jika berbeda dari skor terakhir
                        if skor_final != app_state["last_logged_score"]:
                            app_state["last_logged_score"] = skor_final

                            if df_win is not None:
                                threading.Thread(
                                    target=tulis_log_ke_csv,
                                    args=(nama_gerakan, skor_final, df_win),
                                    daemon=True
                                ).start()

                    # Kosongkan buffer setelah gerakan selesai
                    app_state["score_holding_buffer"] = []

                # Sliding window
                app_state["window_buffer"] = app_state["window_buffer"][SLIDE_STEP:]

    except Exception as e:
        print(f"[MQTT] Error parsing: {e}")

# ==========================================
# 8. MQTT CLIENT SETUP — AUTO RECONNECT
# ==========================================
def init_mqtt():
    def mqtt_loop():
        attempt = 0

        while True:
            try:
                attempt += 1

                with state_lock:
                    app_state["mqtt_reconnect_count"] = attempt

                print(f"[MQTT] 🔄 Percobaan koneksi ke {MQTT_BROKER}:1883 (ke-{attempt})...")

                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)

                client.on_connect    = on_connect
                client.on_disconnect = on_disconnect
                client.on_message    = on_message

                client.connect(MQTT_BROKER, 1883, keepalive=60)
                client.loop_forever()

            except Exception as e:
                print(f"[MQTT] ❌ Koneksi gagal: {e}")

            with state_lock:
                app_state["mqtt_connected"] = False

            print(f"[MQTT] ⏳ Reconnect dalam {RECONNECT_DELAY} detik...")
            time.sleep(RECONNECT_DELAY)

    t = threading.Thread(
        target=mqtt_loop,
        daemon=True,
        name="mqtt-reconnect-thread"
    )

    t.start()

    print("[MQTT] Thread auto-reconnect dimulai.")

# ==========================================
# 9. REST API ENDPOINTS
# ==========================================

@app.route("/")
def index():
    return render_template("index.html", gerakan_list=GERAKAN_LIST)

@app.route("/api/latest-data", methods=["GET"])
def api_latest_data():
    """Nilai sensor terbaru + buffer chart + status koneksi"""

    with state_lock:
        d         = list(app_state["latest_data"])
        buf       = list(app_state["sensor_buffer"])
        connected = app_state["mqtt_connected"]
        reconnect = app_state["mqtt_reconnect_count"]

    sensor1 = {
        "ax": d[0],
        "ay": d[1],
        "az": d[2],
        "gx": d[3],
        "gy": d[4],
        "gz": d[5],
    }

    sensor2 = {
        "ax": d[6],
        "ay": d[7],
        "az": d[8],
        "gx": d[9],
        "gy": d[10],
        "gz": d[11],
    }

    chart_data = []

    for row in buf:
        chart_data.append({
            "ax1": row[0],
            "ay1": row[1],
            "az1": row[2],
            "gx1": row[3],
            "gy1": row[4],
            "gz1": row[5],
            "ax2": row[6],
            "ay2": row[7],
            "az2": row[8],
            "gx2": row[9],
            "gy2": row[10],
            "gz2": row[11],
        })

    return jsonify({
        "sensor1"          : sensor1,
        "sensor2"          : sensor2,
        "chart_data"       : chart_data,
        "connected"        : connected,
        "reconnect_attempt": reconnect,
    })

@app.route("/api/prediction", methods=["GET"])
def api_prediction():
    """Skor prediksi AI terkini"""

    with state_lock:
        skor         = app_state["current_score"]
        nama_gerakan = app_state["selected_model"]

    model_ready = models_dict.get(nama_gerakan) is not None

    if skor is None:
        status = "waiting"
        label  = "Menunggu Data..."

    elif skor == -1:
        status = "measuring"
        label  = "Mengukur Gerakan..."

    else:
        status = "scored"
        label  = SKOR_LABEL.get(skor, "-")

    return jsonify({
        "score"      : skor,
        "status"     : status,
        "label"      : label,
        "movement"   : nama_gerakan,
        "model_ready": model_ready,
    })

@app.route("/api/history", methods=["GET"])
def api_history():
    """Riwayat prediksi dari CSV"""

    try:
        if not os.path.exists(LOG_FILE_PATH) or os.path.getsize(LOG_FILE_PATH) == 0:
            return jsonify({
                "data" : [],
                "total": 0
            })

        df = pd.read_csv(LOG_FILE_PATH, sep=";")

        kolom_baru = [
            "Waktu_Uji",
            "Gerakan_ARAT",
            "Prediksi_Skor_AI"
        ]

        kolom_lama = [
            "Waktu",
            "Gerakan",
            "Skor"
        ]

        if all(k in df.columns for k in kolom_baru):
            df_show = df[kolom_baru].copy()
            df_show.columns = [
                "waktu",
                "gerakan",
                "skor"
            ]

        elif all(k in df.columns for k in kolom_lama):
            df_show = df[kolom_lama].copy()
            df_show.columns = [
                "waktu",
                "gerakan",
                "skor"
            ]

        else:
            df_show = df.iloc[:, :3].copy()
            df_show.columns = [
                "waktu",
                "gerakan",
                "skor"
            ]

        def safe_int(s):
            try:
                return int(float(s))
            except:
                return 0

        df_show["skor"] = df_show["skor"].apply(safe_int)

        df_show["keterangan"] = df_show["skor"].apply(
            lambda s: SKOR_LABEL.get(s, "-")
        )

        df_show = df_show.iloc[::-1].reset_index(drop=True)

        records = df_show.to_dict(orient="records")

        return jsonify({
            "data" : records,
            "total": len(records)
        })

    except Exception as e:
        return jsonify({
            "data" : [],
            "total": 0,
            "error": str(e)
        })

@app.route("/api/model-status", methods=["GET"])
def api_model_status():
    """Status semua model .pkl"""

    status = {}

    for name in GERAKAN_LIST:
        status[name] = models_dict.get(name) is not None

    return jsonify(status)

@app.route("/select-model", methods=["POST"])
def select_model():
    """Ganti model gerakan aktif dari frontend"""

    data    = request.get_json()
    gerakan = data.get("gerakan", "").strip()

    if gerakan not in GERAKAN_LIST:
        return jsonify({
            "success": False,
            "message": "Gerakan tidak dikenal"
        }), 400

    with state_lock:
        app_state["selected_model"]       = gerakan
        app_state["current_score"]        = None
        app_state["window_buffer"]        = []
        app_state["score_holding_buffer"] = []
        app_state["last_logged_score"]    = None

    model_ready = models_dict.get(gerakan) is not None

    print(f"[MODEL] Beralih ke: {gerakan} | Ready: {model_ready}")

    return jsonify({
        "success"    : True,
        "gerakan"    : gerakan,
        "model_ready": model_ready,
    })

@app.route("/download-log", methods=["GET"])
def download_log():
    """Download file log CSV"""

    if not os.path.exists(LOG_FILE_PATH) or os.path.getsize(LOG_FILE_PATH) == 0:
        return jsonify({
            "error": "Log belum tersedia"
        }), 404

    filename = f"log_latihan_arat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return send_file(
        LOG_FILE_PATH,
        mimetype="text/csv",
        as_attachment=True,
        download_name=filename
    )

# ==========================================
# 10. ENTRY POINT
# ==========================================
if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)

    init_mqtt()

    print("\n" + "="*50)
    print("  RehabStroke AI - Flask Server v3.0")
    print("  http://127.0.0.1:5000")
    print("="*50 + "\n")

    app.run(
        debug=True,
        use_reloader=False,
        host="0.0.0.0",
        port=5000
    )