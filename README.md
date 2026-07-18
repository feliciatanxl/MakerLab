# Maker-Lab

A collection of Arduino, ESP32, Raspberry Pi, and embedded systems projects.

Maker-Lab is a long-term personal maker repository for learning through hardware, software, and experimentation. It brings together source code, build notes, and a public-facing website for electronics, IoT, embedded systems, sensors, and hardware-and-software prototypes.

> **Tagline:** Building ideas through hardware, software, and experimentation.

## Website overview

The repository includes a responsive static portfolio built with semantic HTML, modern CSS, and vanilla JavaScript. Its visual direction combines an electronics workbench, PCB traces, embedded-system readouts, and clean project documentation.

The website includes:

- A responsive homepage with project filters and an editable build log
- A genuine featured-project section for EchoSync
- A dedicated EchoSync technical detail page
- Technology and learning-area summaries without artificial proficiency scores
- Accessible navigation, focus states, reduced-motion support, and mobile layouts
- Static files that can be opened locally or deployed directly to Vercel

## Current projects

| Project | Platform | Status |
| --- | --- | --- |
| EchoSync | Arduino + Raspberry Pi | Built Prototype |
| ESP32 Hologram Cube | ESP32 | Planned |
| LED Matrix Tetris | Arduino | Planned |
| RFID Access System | ESP32 | Planned |
| Sensor Playground | Arduino + ESP32 | Planned |

Planned projects are roadmap entries, not completed builds.

## EchoSync

EchoSync is the first genuine project in Maker-Lab. It is a privacy-conscious wellbeing and emergency-detection prototype that connects ambient sensors, Arduino firmware, Raspberry Pi decision and voice logic, and a broader digital response application.

The checked-in Arduino sketch reads a microphone/sound sensor, PIR motion sensor, ultrasonic sensor, and HX711-connected load cell, displays local status on an I²C LCD, and sends JSON data over serial. The Raspberry Pi Python program reads and enriches that serial data and includes audio and HTTP communication workflows.

The complete EchoSync application ecosystem—including the operator-style dashboard, caregiver and responder views, public website, and API routes—is maintained separately:

- **Full application repository:** [github.com/feliciatanxl/EchoSync](https://github.com/feliciatanxl/EchoSync)
- **Maker-Lab case study:** [`projects/echosync.html`](projects/echosync.html)

The case study includes English and Chinese demonstration videos, a hardware gallery, an accessible image lightbox, the Arduino-to-Raspberry Pi serial flow, and a clear distinction between the built prototype and future improvements. EchoSync is an innovation prototype, not a certified medical device or deployed emergency system.

### EchoSync documentation roles

Maker-Lab contains the technical EchoSync build documentation: the hardware prototype, sensor roles, Arduino-to-Raspberry Pi workflow, serial JSON, architecture, short hardware demonstrations, source code, and engineering lessons.

The [EchoSync portfolio case study](https://feliciatanxl.github.io/Portfolio/echosync.html) contains the wider project story, problem and impact, personal contribution summary, competition journey, and application walkthrough. The two pages are intentionally cross-linked so each can stay focused on its own role. A future full application walkthrough should live on the portfolio page, while shorter hardware demonstrations remain in Maker-Lab.

Source files:

- [`EchoSync/EchoSync.ino`](EchoSync/EchoSync.ino) — Arduino sensor-node firmware
- [`EchoSync/EchoTest_Pi.py`](EchoSync/EchoTest_Pi.py) — Raspberry Pi Python workflow

## Repository structure

```text
MakerLab/
├── index.html
├── projects/
│   └── echosync.html
├── css/
│   ├── styles.css
│   └── project.css
├── js/
│   ├── app.js
│   └── projects-data.js
├── assets/
│   ├── icons/
│   ├── images/
│   │   └── echosync/
│   └── videos/
│       └── echosync/
├── EchoSync/
│   ├── EchoSync.ino
│   └── EchoTest_Pi.py
├── vercel.json
├── README.md
└── .gitignore
```

The `assets` folders contain original project photography, demonstration media, and Maker-Lab icons. The site does not depend on external stock imagery.

## EchoSync media

```text
assets/
├── images/
│   └── echosync/
│       ├── full_closeup_view.jpg
│       ├── analog-sound-sensor.jpg
│       ├── esp32-cam.jpg
│       ├── infrared-sensor-module.jpg
│       ├── inmp441-microphone.jpg
│       ├── load-cell-hx711.jpg
│       ├── pir-motion-sensor.jpg
│       ├── speaker-pair.jpg
│       ├── ultrasonic-sensor.jpg
│       └── usb-audio-adapter.jpg
└── videos/
    └── echosync/
        ├── echosync-demo-english.mp4
        └── echosync-demo-chinese.mp4
```

The hero image loads immediately. Gallery and hardware-card images use native lazy loading, while both videos use `preload="metadata"` and never autoplay.

### Replace project media

1. Keep replacement images in `assets/images/echosync/` and videos in `assets/videos/echosync/`.
2. Use descriptive lowercase filenames and retain web-compatible formats such as JPEG and MP4.
3. Update the corresponding `image`, `hardware`, `gallery`, or `videos` entry in [`js/projects-data.js`](js/projects-data.js).
4. Keep meaningful `alt` text and captions in the same central data object.
5. Preview the homepage and case-study page before committing.

### Optimise videos

If FFmpeg is available, a large demonstration can be converted to a web-friendly H.264/AAC MP4 at approximately 720p:

```bash
ffmpeg -i input.mp4 -vf "scale=-2:720" -c:v libx264 -crf 26 -preset medium -c:a aac -b:a 96k -movflags +faststart output.mp4
```

Before replacing the repository copy, verify that the output plays from beginning to end, contains its audio track, preserves the expected duration, and is smaller than the original. Keep only the verified delivery file rather than committing unnecessary duplicates.

## Run the website locally

No package installation or build step is required.

From the repository root, start a simple static server:

```bash
python -m http.server 8000
```

Then open:

```text
http://localhost:8000/
```

The EchoSync page is available at:

```text
http://localhost:8000/projects/echosync.html
```

You can also open `index.html` directly, although a local server more closely matches a deployed environment.

## Deploy to Vercel

### Vercel dashboard

1. Push the repository to GitHub.
2. In Vercel, choose **Add New → Project**.
3. Import the `MakerLab` GitHub repository.
4. Leave the framework preset as **Other**.
5. Leave the build command empty and use `.` as the output directory if Vercel asks for one.
6. Select **Deploy**.

### Vercel CLI

```bash
npm install -g vercel
vercel
```

Accept the default project root and do not add a build command. For a production deployment, run:

```bash
vercel --prod
```

No server, database, environment variable, or build step is required for the website.

**Deployed website:** `https://your-project-name.vercel.app`

## Add another project

Project cards and build-log entries are controlled from [`js/projects-data.js`](js/projects-data.js).

1. Add a new object to the `projects` array.
2. Give it a unique `id`, project name, grounded description, platform, status, filters, and technology tags.
3. Use `status: "Planned"` until the project is genuinely built.
4. Add a relative `detailUrl` only after creating a corresponding page in `projects/`.
5. Add a build-log entry to the `buildLog` array when there is a real milestone to record.

The homepage cards and filter results render automatically from that central data file. EchoSync’s detailed hardware, software, capabilities, flow, and source-file links are stored there as well.

## Technologies used

- Semantic HTML5
- Modern CSS with custom properties, grid, and flexbox
- Vanilla JavaScript
- Arduino C/C++
- Python
- Serial communication and JSON
- Sensors and embedded-system interfaces

## Design principles

- Document real work and label future ideas honestly
- Keep project information easy to update from one data source
- Prefer lightweight, dependency-free web code
- Preserve accessible keyboard, touch, and reduced-motion experiences
- Grow the repository alongside the projects and lessons it records
