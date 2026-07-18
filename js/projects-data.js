(function () {
  "use strict";

  const repositoryUrl = "https://github.com/feliciatanxl/MakerLab";
  const echoSyncRepositoryUrl = "https://github.com/feliciatanxl/EchoSync";
  const echoSyncPortfolioUrl = "https://feliciatanxl.github.io/Portfolio/echosync.html";
  const echoSyncPrototypeImages = [
    {
      image: "assets/images/echosync/echosync-prototype-front.jpg",
      width: 720,
      height: 1280,
      alt: "Front view of the EchoSync Arduino development prototype with an ultrasonic sensor, breadboard, and status LEDs",
      caption: "Front view of the EchoSync development prototype with ultrasonic sensing, status LEDs, and connected Arduino hardware.",
      category: "Integrated prototype"
    },
    {
      image: "assets/images/echosync/echosync-prototype-overhead.jpg",
      width: 720,
      height: 1280,
      alt: "Overhead view of the EchoSync Arduino prototype with breadboard, ultrasonic sensor, LEDs, and connected modules",
      caption: "Overhead development view of the integrated Arduino sensing prototype.",
      category: "Integrated prototype"
    },
    {
      image: "assets/images/echosync/echosync-lcd-loadcell-integration.jpg",
      width: 720,
      height: 1280,
      alt: "EchoSync Arduino prototype connected to an LCD display and load-cell assembly during testing",
      caption: "LCD feedback and load-cell integration during prototype testing.",
      category: "Sensor integration"
    },
    {
      image: "assets/images/echosync/echosync-raspberry-pi-audio-setup.jpg",
      width: 1280,
      height: 720,
      alt: "Raspberry Pi connected to a USB audio adapter, speaker, and EchoSync Arduino prototype",
      caption: "Raspberry Pi audio and decision workflow connected to the Arduino sensor prototype.",
      category: "Edge audio workflow"
    },
    {
      image: "assets/images/echosync/echosync-end-to-end-test.jpg",
      width: 1280,
      height: 720,
      alt: "Complete EchoSync test setup with Raspberry Pi, Arduino prototype, sensors, and LCD status display",
      caption: "End-to-end EchoSync hardware test linking sensing, serial communication, voice feedback, and status display.",
      category: "End-to-end test"
    }
  ];

  const projects = [
    {
      id: "echosync",
      slug: "echosync",
      order: 1,
      name: "EchoSync",
      status: "Built Prototype",
      platform: "Arduino + Raspberry Pi",
      platformLabel: "Arduino · Raspberry Pi · Sensors · IoT",
      description: "A privacy-conscious wellbeing and emergency-detection prototype connecting ambient sensors, edge decision logic, voice check-ins, and a digital response workflow.",
      featuredDescription: "Sensors and Arduino firmware feed serial JSON to a Raspberry Pi workflow, which can request spoken confirmation and pass structured incident data to the broader EchoSync application ecosystem.",
      filters: ["Arduino", "Raspberry Pi", "IoT"],
      tags: ["Sensors", "Python", "Serial JSON", "Application ecosystem"],
      detailUrl: "projects/echosync.html",
      repositoryUrl: echoSyncRepositoryUrl,
      portfolioUrl: echoSyncPortfolioUrl,
      sourceUrl: `${repositoryUrl}/tree/main/EchoSync`,
      image: echoSyncPrototypeImages[0].image,
      imageAlt: echoSyncPrototypeImages[0].alt,
      firmwareLinks: [
        {
          name: "EchoSync.ino",
          path: "EchoSync/EchoSync.ino",
          role: "Arduino sensor-node firmware"
        },
        {
          name: "EchoTest_Pi.py",
          path: "EchoSync/EchoTest_Pi.py",
          role: "Raspberry Pi decision, audio, and HTTP workflow"
        }
      ],
      videos: [
        {
          language: "English",
          title: "English Demonstration",
          description: "English walkthrough showing EchoSync listening for a help request, requesting confirmation and escalating the incident for review.",
          src: "assets/videos/echosync/echosync-demo-english.mp4"
        },
        {
          language: "中文",
          title: "中文演示",
          description: "Chinese-language walkthrough showing the same detection, confirmation and escalation process.",
          src: "assets/videos/echosync/echosync-demo-chinese.mp4"
        }
      ],
      detail: {
        summary: "EchoSync is a privacy-conscious wellbeing and emergency-detection prototype that combines environmental sensors, Arduino firmware, Raspberry Pi decision logic, and a digital response platform to recognise possible distress and coordinate escalating assistance.",
        prototypeNotice: "EchoSync is an innovation prototype. It is not a certified medical device, a clinically validated system, or a deployed emergency service.",
        overview: "The embedded prototype observes changes in sound, motion, distance, and load. It combines those signals with a Raspberry Pi voice workflow before preparing structured information for human review in the wider EchoSync application.",
        prototypeImages: echoSyncPrototypeImages,
        hardware: [
          {
            name: "Arduino sensor node",
            purpose: "Collects the checked-in sound, PIR, ultrasonic, and load-cell readings; drives the I²C LCD and status LEDs; and emits serial JSON.",
            interface: "Analog + digital GPIO · I²C · USB serial",
            image: "assets/images/echosync/echosync-prototype-overhead.jpg",
            width: 720,
            height: 1280,
            crop: "prototype-overhead",
            alt: "Overhead view of the EchoSync Arduino sensor node with breadboard, ultrasonic sensor, LEDs, and connected modules"
          },
          {
            name: "Raspberry Pi edge host",
            purpose: "Reads the Arduino serial stream, applies decision and voice-response logic, and sends structured information to configured HTTP endpoints.",
            interface: "USB serial · USB audio · HTTP/API",
            image: "assets/images/echosync/echosync-raspberry-pi-audio-setup.jpg",
            width: 1280,
            height: 720,
            crop: "raspberry-pi-audio",
            alt: "Raspberry Pi edge setup with Raspberry Pi, USB audio adapter, speaker, and connected Arduino hardware"
          },
          {
            name: "HC-SR501 PIR motion sensor",
            purpose: "Provides a digital indication of motion for the prototype’s activity and timing logic.",
            interface: "Digital GPIO",
            image: "assets/images/echosync/pir-motion-sensor.jpg",
            alt: "HC-SR501 PIR motion sensor inside protective packaging"
          },
          {
            name: "HC-SR04 ultrasonic sensor",
            purpose: "Measures distance and supports near-object and distance-change observations.",
            interface: "Trigger + echo digital GPIO",
            image: "assets/images/echosync/ultrasonic-sensor.jpg",
            alt: "HC-SR04 ultrasonic distance sensor inside an antistatic bag"
          },
          {
            name: "Analog sound sensor",
            purpose: "Supplies the Arduino with analogue sound-level variation and a digital trigger state.",
            interface: "Analog input + digital GPIO",
            image: "assets/images/echosync/analog-sound-sensor.jpg",
            alt: "Red analogue sound sensor module in protective packaging"
          },
          {
            name: "HX711 and load cell",
            purpose: "Captures load changes after a startup tare, adding another physical signal to the decision workflow.",
            interface: "HX711 data + clock interface",
            image: "assets/images/echosync/load-cell-hx711.jpg",
            alt: "Metal load cell and green HX711 amplifier board mounted on a clear circular plate"
          },
          {
            name: "Speaker pair",
            purpose: "Provides local voice prompts and spoken feedback during confirmation flows.",
            interface: "Raspberry Pi audio output",
            image: "assets/images/echosync/speaker-pair.jpg",
            alt: "Pair of compact black speakers with red and black leads"
          },
          {
            name: "USB audio adapter",
            purpose: "Makes audio input or output available to the Raspberry Pi over USB for the prototype voice workflow.",
            interface: "USB audio",
            image: "assets/images/echosync/usb-audio-adapter.jpg",
            alt: "White product box labelled USB to Audio"
          },
          {
            name: "INMP441 microphone",
            purpose: "An available omnidirectional digital microphone module explored for audio capture; it is not referenced by the checked-in Arduino sketch.",
            interface: "I²S digital audio",
            image: "assets/images/echosync/inmp441-microphone.jpg",
            alt: "INMP441 omnidirectional microphone module inside an antistatic bag"
          },
          {
            name: "ESP32-CAM",
            purpose: "An explored camera-capable module available during prototyping; the checked-in Arduino and Raspberry Pi detection pipeline does not depend on it.",
            interface: "ESP32 camera development module",
            image: "assets/images/echosync/esp32-cam.jpg",
            alt: "Small black ESP32-CAM development module held between two fingers"
          }
        ],
        architecture: [
          { title: "Physical environment", label: "Ambient activity" },
          { title: "Sensor inputs", label: "Sound · PIR · Ultrasonic · Load" },
          { title: "Arduino sensor node", label: "Read · Display · Serialize" },
          { title: "USB serial", label: "Structured JSON · 115200 baud" },
          { title: "Raspberry Pi", label: "Decision + audio workflow" },
          { title: "HTTP/API", label: "Structured incident exchange" },
          { title: "EchoSync application", label: "Dashboard + response views" },
          { title: "Response and escalation", label: "Human review · Caregiver · Responder" }
        ],
        detectionWorkflow: [
          { title: "Monitoring", text: "The system continuously reads the available sensor values." },
          { title: "Possible distress detected", text: "A sensor combination or a recognised help request can start a check-in flow." },
          { title: "Confirmation requested", text: "EchoSync plays a spoken prompt and listens for a response." },
          { title: "Response evaluated", text: "The workflow distinguishes help, okay, unclear, and no-response outcomes." },
          { title: "Alert level adjusted", text: "Confirmed distress or no response can increase the level used for review." },
          { title: "Alert escalated", text: "A structured incident is sent to the relevant demonstration workflow for human review." }
        ],
        serialExample: {
          soundLevel: 184,
          micDigital: 0,
          pirMotion: 1,
          distanceCm: 42.6,
          soundDetected: 1,
          nearDetected: 1,
          loadReady: 1,
          loadRaw: 120000,
          loadNet: 8120,
          loadDetected: 1,
          possibleFall: 1,
          alert: 1
        },
        ecosystem: [
          { title: "Sensor prototype", label: "Arduino + physical inputs" },
          { title: "Raspberry Pi edge workflow", label: "Decision + voice response" },
          { title: "EchoSync APIs", label: "Structured incident data" },
          { title: "Application interfaces", label: "Operator, caregiver, responder + public site" }
        ],
        gallery: [
          ...echoSyncPrototypeImages,
          { image: "assets/images/echosync/full_closeup_view.jpg", alt: "Complete EchoSync prototype with Arduino, Raspberry Pi, LCD, load cell, breadboard, and wiring", caption: "Full EchoSync hardware prototype" },
          { image: "assets/images/echosync/speaker-pair.jpg", alt: "Two compact black speakers with red and black wires", caption: "Speaker pair for local voice feedback" },
          { image: "assets/images/echosync/usb-audio-adapter.jpg", alt: "White packaging labelled USB to Audio", caption: "USB audio adapter packaging used for the Raspberry Pi audio setup" },
          { image: "assets/images/echosync/pir-motion-sensor.jpg", alt: "HC-SR501 PIR sensor visible through an antistatic bag", caption: "HC-SR501 PIR motion sensor" },
          { image: "assets/images/echosync/inmp441-microphone.jpg", alt: "INMP441 microphone module visible through an antistatic bag", caption: "INMP441 digital microphone module explored for audio capture" },
          { image: "assets/images/echosync/ultrasonic-sensor.jpg", alt: "HC-SR04 ultrasonic sensor with two circular transducers", caption: "HC-SR04 ultrasonic distance sensor" },
          { image: "assets/images/echosync/analog-sound-sensor.jpg", alt: "Red analogue sound sensor module in a protective bag", caption: "Analogue sound sensor used by the Arduino node" },
          { image: "assets/images/echosync/esp32-cam.jpg", alt: "Black ESP32-CAM board with a small camera lens", caption: "ESP32-CAM explored as an available development module" },
          { image: "assets/images/echosync/load-cell-hx711.jpg", alt: "Metal load cell wired to a green HX711 amplifier board", caption: "Load cell and HX711 amplifier assembly" },
          { image: "assets/images/echosync/infrared-sensor-module.jpg", alt: "Small blue infrared sensor module in a clear bag", caption: "Infrared sensor module available during prototyping; not part of the checked-in detection pipeline" }
        ],
        results: [
          "Combined multiple physical sensor inputs in one Arduino prototype",
          "Sent structured data from Arduino to Raspberry Pi over USB serial",
          "Added spoken confirmation before escalation decisions",
          "Demonstrated English and Chinese interaction flows",
          "Connected physical sensing to a digital application workflow",
          "Produced a working end-to-end prototype demonstration"
        ],
        recognition: "Top 10 shortlisted, later selected as a Top 5 finalist out of 81 teams.",
        lessons: [
          "Noisy physical signals need timing windows, baselines, and combination logic rather than a single threshold.",
          "Line-delimited serial JSON makes the Arduino–Raspberry Pi boundary visible and easier to inspect.",
          "Voice-response handling must account for help, okay, unclear speech, and silence without treating every ambiguity as certainty.",
          "Connecting physical hardware to APIs requires careful timeout and failure handling when endpoints are unavailable.",
          "Escalation logic benefits from a human-review step and clear evidence instead of unsupported automation claims."
        ],
        future: [
          "Better sensor fusion",
          "Improved voice-intent recognition",
          "More robust offline operation",
          "Improved enclosure and cable management",
          "More testing under realistic environmental conditions",
          "Secure deployment and authentication",
          "Additional accessibility and language support"
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
    echoSyncRepositoryUrl,
    filters: ["All", "Arduino", "ESP32", "Raspberry Pi", "IoT", "Planned"],
    projects,
    buildLog
  });
}());
