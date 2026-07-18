(function () {
  "use strict";

  const repositoryUrl = "https://github.com/feliciatanxl/MakerLab";

  const projects = [
    {
      id: "echosync",
      order: 1,
      name: "EchoSync",
      description: "A multi-sensor Arduino node paired with Raspberry Pi software for reading, enriching, and communicating sensor events.",
      platform: "Arduino + Raspberry Pi",
      status: "Built",
      filters: ["Arduino", "Raspberry Pi", "IoT"],
      tags: ["Arduino", "Python", "Serial JSON", "Sensors"],
      detailUrl: "projects/echosync.html",
      sourceUrl: `${repositoryUrl}/tree/main/EchoSync`,
      featuredDescription: "The Arduino sketch combines sound, motion, distance, and load-cell inputs, displays local status on an I²C LCD, and sends JSON over serial to the Python component.",
      detail: {
        summary: "EchoSync connects an Arduino sensor node to Raspberry Pi software. The Arduino gathers several physical inputs, reports local state through LEDs and an I²C LCD, and emits structured JSON over a 115200-baud serial connection. The Python program reads that stream, adds decision logic, supports audio workflows, and communicates with HTTP endpoints.",
        hardware: [
          "Arduino-compatible board",
          "Raspberry Pi",
          "KY-038 microphone / sound sensor",
          "PIR motion sensor",
          "Ultrasonic distance sensor",
          "HX711 load-cell interface and load cell",
          "16×2 I²C LCD",
          "Status LEDs"
        ],
        software: [
          "Arduino C/C++ sketch",
          "Python 3",
          "PySerial serial communication",
          "JSON sensor messages",
          "HTTP requests / API communication",
          "Linux audio command-line tools"
        ],
        communication: "Once per second, the Arduino sketch serializes sensor state as a JSON line and sends it over USB serial at 115200 baud. The Raspberry Pi Python program reads each line, ignores non-JSON status text, parses valid messages, and enriches the readings before applying its response and communication logic.",
        flow: [
          { title: "Sensors", label: "Sound · PIR · Distance · Load" },
          { title: "Arduino", label: "Read · Display · Serialize" },
          { title: "USB serial", label: "JSON lines · 115200 baud" },
          { title: "Raspberry Pi", label: "Parse · Enrich · Respond" }
        ],
        capabilities: [
          "Reads sound level and digital sound state",
          "Detects PIR motion",
          "Measures ultrasonic distance",
          "Reads and tares an HX711-connected load cell",
          "Shows local state on an I²C LCD and status LEDs",
          "Streams structured sensor data to Raspberry Pi software",
          "Uses sensor combinations and timing windows in its decision logic",
          "Sends HTTP requests to configured application endpoints"
        ],
        files: [
          {
            name: "EchoSync.ino",
            role: "Arduino sensor-node firmware",
            url: `${repositoryUrl}/blob/main/EchoSync/EchoSync.ino`
          },
          {
            name: "EchoTest_Pi.py",
            role: "Raspberry Pi serial, decision, audio, and HTTP workflow",
            url: `${repositoryUrl}/blob/main/EchoSync/EchoTest_Pi.py`
          }
        ]
      }
    },
    {
      id: "esp32-hologram-cube",
      order: 2,
      name: "ESP32 Hologram Cube",
      description: "A planned ESP32 exploration focused on coordinating a compact visual hardware build.",
      platform: "ESP32",
      status: "Planned",
      filters: ["ESP32", "Planned"],
      tags: ["ESP32", "Embedded systems", "Prototype"],
      detailUrl: null
    },
    {
      id: "led-matrix-tetris",
      order: 3,
      name: "LED Matrix Tetris",
      description: "A planned embedded game experiment for learning matrix displays, inputs, and timing logic.",
      platform: "Arduino",
      status: "Planned",
      filters: ["Arduino", "Planned"],
      tags: ["Arduino", "LED matrix", "C/C++"],
      detailUrl: null
    },
    {
      id: "rfid-access-system",
      order: 4,
      name: "RFID Access System",
      description: "A planned prototype for exploring RFID reading and physical access-control feedback.",
      platform: "ESP32",
      status: "Planned",
      filters: ["ESP32", "IoT", "Planned"],
      tags: ["ESP32", "RFID", "IoT"],
      detailUrl: null
    },
    {
      id: "sensor-playground",
      order: 5,
      name: "Sensor Playground",
      description: "A planned collection of small tests for learning how different sensors behave and connect.",
      platform: "Arduino + ESP32",
      status: "Planned",
      filters: ["Arduino", "ESP32", "IoT", "Planned"],
      tags: ["Sensors", "Arduino", "ESP32"],
      detailUrl: null
    }
  ];

  const buildLog = [
    {
      title: "Maker-Lab repository created",
      description: "A dedicated home for electronics, embedded systems, IoT, and project documentation.",
      status: "Completed",
      phase: "Foundation"
    },
    {
      title: "EchoSync source added",
      description: "Arduino firmware and Raspberry Pi Python software became the repository’s first genuine project source.",
      status: "Completed",
      phase: "Project 001"
    },
    {
      title: "Maker-Lab website created",
      description: "A responsive public showcase and documentation entry point was added to the repository.",
      status: "Completed",
      phase: "Website 001"
    },
    {
      title: "ESP32 experiments planned",
      description: "Future bench sessions will explore ESP32-based prototypes and connected devices.",
      status: "Planned",
      phase: "Next"
    },
    {
      title: "Arduino R4 experiments planned",
      description: "Arduino R4 investigations are queued for future hardware learning and documentation.",
      status: "Planned",
      phase: "Queued"
    },
    {
      title: "Raspberry Pi projects planned",
      description: "More Raspberry Pi software-and-hardware integrations will be added as they are built.",
      status: "Planned",
      phase: "Queued"
    }
  ];

  window.MAKER_LAB_DATA = Object.freeze({
    repositoryUrl,
    filters: ["All", "Arduino", "ESP32", "Raspberry Pi", "IoT", "Planned"],
    projects,
    buildLog
  });
}());
