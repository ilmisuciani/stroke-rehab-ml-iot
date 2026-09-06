#include <WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Wire.h>

const char* ssid = "hotspot ilmi";
const char* password = "12345678";
const char* mqtt_server = "broker.emqx.io";

WiFiClient espClient;
PubSubClient client(espClient);
Adafruit_MPU6050 mpu1;
Adafruit_MPU6050 mpu2;

void setup() {
  Serial.begin(115200);
  delay(1000); // Beri waktu hardware untuk stabil setelah power menyala

  // 1. Inisialisasi Jalur I2C (Harus PALING AWAL)
  Wire.begin(21, 22);
  Wire.setClock(400000); // Set kecepatan ke 400kHz agar transfer data sensor mulus
  delay(500);

  // 2. Inisialisasi MPU ke-1 (0x68)
  Serial.print("Mencari MPU6050 #1 (0x68)...");
  if (!mpu1.begin(0x68)) {
    Serial.println(" GAGAL! Periksa kabel SDA/SCL.");
    // Kita tidak pakai while(1) agar program tidak macet total jika salah satu sensor lepas
  } else {
    Serial.println(" BERHASIL!");
  }

  // 3. Inisialisasi MPU ke-2 (0x69)
  delay(200); // Jeda singkat agar tidak bentrok di jalur data
  Serial.print("Mencari MPU6050 #2 (0x69)...");
  if (!mpu2.begin(0x69)) {
    Serial.println(" GAGAL! Pastikan pin AD0 ke VCC.");
  } else {
    Serial.println(" BERHASIL!");
  }

  // 4. Baru hubungkan ke WiFi setelah urusan sensor selesai
  Serial.println("\n--- Mengaktifkan WiFi ---");
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nWiFi Terhubung!");
  
  client.setServer(mqtt_server, 1883);
}

void reconnect() {
  while (!client.connected()) {
    Serial.print("Mencoba koneksi MQTT...");
    // Gunakan ID unik agar tidak bentrok dengan user lain di broker publik
    if (client.connect("ESP32_Ilmi_Skripsi_Final")) { 
      Serial.println("Terhubung!");
    } else {
      Serial.print("Gagal, rc=");
      Serial.print(client.state());
      Serial.println(" Coba lagi dalam 5 detik...");
      delay(5000);
    }
  }
}

void loop() {
  if (!client.connected()) reconnect();
  client.loop();

  sensors_event_t a1, g1, t1;
  sensors_event_t a2, g2, t2;
  
  // Ambil data
  mpu1.getEvent(&a1, &g1, &t1);
  mpu2.getEvent(&a2, &g2, &t2);

  // Jika hasilnya masih 0, paksa MPU untuk tidak tidur (Wake up command)
  if (a1.acceleration.x == 0 && a1.acceleration.y == 0) {
      Wire.beginTransmission(0x68);
      Wire.write(0x6B); // PWR_MGMT_1 register
      Wire.write(0);    // Set ke 0 untuk bangun
      Wire.endTransmission();
  }
  if (a2.acceleration.x == 0 && a2.acceleration.y == 0) {
      Wire.beginTransmission(0x69);
      Wire.write(0x6B); 
      Wire.write(0);    
      Wire.endTransmission();
  }

  // Kirim data (Gunakan desimal 2 saja dulu untuk meringankan beban kirim)
// --- BAGIAN BARU (Akselerometer + Gyroscope) ---
String payload = String(a1.acceleration.x, 2) + "," + 
                 String(a1.acceleration.y, 2) + "," + 
                 String(a1.acceleration.z, 2) + "," +
                 String(g1.gyro.x, 2) + "," +          // Data Gyro 1 X
                 String(g1.gyro.y, 2) + "," +          // Data Gyro 1 Y
                 String(g1.gyro.z, 2) + "," +          // Data Gyro 1 Z
                 String(a2.acceleration.x, 2) + "," + 
                 String(a2.acceleration.y, 2) + "," + 
                 String(a2.acceleration.z, 2) + "," +
                 String(g2.gyro.x, 2) + "," +          // Data Gyro 2 X
                 String(g2.gyro.y, 2) + "," +          // Data Gyro 2 Y
                 String(g2.gyro.z, 2);                 // Data Gyro 2 Z
  
  client.publish("skripsi/ilmi/sensor", payload.c_str());
  delay(200); 
}