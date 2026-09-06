# IoT-Based Hand Wearable Sensor with Random Forest for Post-Stroke Rehabilitation (ARAT-Based)

## Overview

An IoT-based hand wearable sensor system that uses a Random Forest algorithm to monitor and classify hand movements of post-stroke patients in real time, based on the Action Research Arm Test (ARAT) criteria.

## Key Features

- **Hardware:** ESP32 microcontroller + 2x MPU6050 sensors (accelerometer & gyroscope), placed on the back of the hand and forearm
- **Machine Learning:** Random Forest classifier with combined balancing (under-sampling + RandomOverSampler) to handle imbalanced data
- **Movements analyzed:** 7 ARAT movements Hand to Mouth, Hand to Tophead, Hand to Backhead, Cup, Big Tube, Small Tube, Ring
- **Dashboard:** Real-time web dashboard showing ARAT scores, activity history, and rehabilitation progress trends

## Project Structure

```
├── firmware/           # ESP32 code for sensor data acquisition
│   └── Perangkat.ino
├── ml-model/           # Data preprocessing, training, and evaluation
│   ├── Model.ipynb
│   └── DATASETACC.csv
├── dashboard/          # Web dashboard for real-time visualization
│   ├── app.py
│   ├── collect.py
│   ├── requirements.txt
│   ├── logs/
│   ├── models/
│   └── templates/
└── README.md
```

## Note

This is a conceptual, prototype-stage undergraduate thesis project. It is not intended for clinical use and has not been validated against conventional ARAT assessment on real patients.
