import paho.mqtt.client as mqtt
import pandas as pd
from datetime import datetime
import os

FILE_NAME = "datasettambahan.csv"
data_buffer = []  # List menampung data sementara
BUFFER_SIZE = 20  # Simpan ke CSV setiap 20 data

# 1. Fungsi saat berhasil terhubung ke broker
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("✅ Terhubung ke Broker! Menunggu data dari ESP32...")
        client.subscribe("skripsi/ilmi/sensor")
    else:
        print(f"❌ Gagal terhubung, kode: {rc}")

# 2. Fungsi saat data masuk
def on_message(client, userdata, msg):
    global data_buffer
    try:
        # Decode data dari ESP32
        payload = msg.payload.decode().split(',')
        
        # Ambil waktu sekarang
        now = datetime.now()
        
        # Pisahkan Tanggal dan Waktu (Presisi Milidetik)
        tanggal = now.strftime("%Y-%m-%d")
        waktu_ms = now.strftime("%H:%M:%S.%f")[:-3] 
        
        # Buat entri data untuk CSV
        # Buat entri data untuk CSV (Lengkap 12 Kolom)
        entry = {
            'Date': tanggal,
            'Time': waktu_ms,
            'ax1': payload[0], 
            'ay1': payload[1], 
            'az1': payload[2],
            'gx1': payload[3], # Tambahan baru
            'gy1': payload[4], # Tambahan baru
            'gz1': payload[5], # Tambahan baru
            'ax2': payload[6], # Pindah indeks dari [3] ke [6]
            'ay2': payload[7], # Pindah indeks dari [4] ke [7]
            'az2': payload[8], # Pindah indeks dari [5] ke [8]
            'gx2': payload[9], # Tambahan baru
            'gy2': payload[10],# Tambahan baru
            'gz2': payload[11] # Tambahan baru
        }
        
        data_buffer.append(entry)
        
        # TAMPILAN TERMINAL: Menampilkan waktu milidetik agar Ilmi bisa pantau
        print(f"[{waktu_ms}] Data ({len(data_buffer)}/{BUFFER_SIZE}): {payload}")

        # Simpan ke CSV jika buffer penuh
        if len(data_buffer) >= BUFFER_SIZE:
            df = pd.DataFrame(data_buffer)
            df.to_csv(FILE_NAME, mode='a', index=False, header=not os.path.exists(FILE_NAME))
            
            print(f"💾 --- BERHASIL SIMPAN {BUFFER_SIZE} DATA KE {FILE_NAME} ---")
            data_buffer.clear() 
            
    except Exception as e:
        print(f"⚠️ Error memproses data: {e}")

# 3. Inisialisasi MQTT Client (Versi 2.0)
client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

print("Menghubungkan ke broker emqx...")
try:
    client.connect("broker.emqx.io", 1883, 60)
    client.loop_forever()
except KeyboardInterrupt:
    if data_buffer:
        df = pd.DataFrame(data_buffer)
        df.to_csv(FILE_NAME, mode='a', index=False, header=not os.path.exists(FILE_NAME))
        print("💾 Sisa data di buffer telah disimpan.")
    print("\nSesi rekaman dihentikan oleh Ilmi.")