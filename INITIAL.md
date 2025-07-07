### FEATURE:
This project aims to build a low-resource, intelligent bedtime storyteller gadget running on a Single-Board Computer (SBC). The core function is to generate and narrate age-appropriate stories in Turkish based on a trigger.
-   **Resource-Constrained Optimization:** The application must be heavily optimized for a Raspberry Pi Zero 2 W, targeting a maximum RAM usage of 350-400MB. All design and dependency choices must prioritize low memory and CPU footprint.
-   **Modular Wakeword Engine:** The system will support multiple wakeword engines (e.g., Porcupine with `.ppn` files, openwakeword with `.onnx` or `.tflite` files). Critically, the system **must** dynamically load **only the one** engine selected in the configuration. The other engine's libraries and models should not be imported or loaded into memory to conserve RAM.
-   **Remote-First AI Processing:** To meet resource constraints, all computationally intensive LLM (story generation) and TTS (narration) tasks are offloaded to remote APIs. Only the active wakeword detection engine runs locally.
-   **Hardware-Aware Audio & Triggers:** The system must feature a hardware abstraction layer to:
    -   Automatically detect and configure the audio output based on the SBC and connected hardware (e.g., IQAudio Codec for Pi Zero 2W, USB audio for RPi 5).
    -   Support multiple activation methods: the locally running wakeword engine, a physical GPIO button press, and a CLI command (`storyteller wake`).
-   **Intelligent Setup & Service Management:** A setup script will identify the host OS (DietPi, Raspberry Pi OS) and SBC model, then apply the correct configurations and install the application as a `systemd` service.
-   **Resource-Efficient Web Interface:** A lightweight web UI will provide comprehensive control, including:
    -   Credentials management for remote LLM/TTS services.
    -   A local story library with CRUD operations.
    -   Story scheduling and a "Do Not Disturb" mode.
    -   Selection and configuration of the active wakeword engine.
-   **Content and Safety:** The primary target user is a 5-year-old, Turkish-speaking girl. All generated content must be strictly age-appropriate. The scheduling and "Do Not Disturb" features are critical safety measures.
### EXAMPLES:

In the `examples/` folder, a `README.md` explains the purpose of each example file. These patterns are the blueprint for all development.

-   **`cli_pattern.py`**: Demonstrates building the command-line interface using `argparse` or `click` to handle user input like the story prompt.
-   **`agent/`**: Exhibits the "Agent" architecture that forms the project's core business logic.
    -   **`agent/agent.py`**: The main orchestrator class. It demonstrates how to take a user prompt and manage the asynchronous flow of generating text and synthesizing audio.
    -   **`agent/providers.py`**: Illustrates the provider pattern for abstracting external services. This allows easily switching between LLM and TTS providers.
    -   **`agent/audio_player.py`**: Shows a pattern for an abstracted audio player to handle playback of synthesized audio data.
-   **`tests/`**: Defines the standards for writing tests.
    -   **`test_agent.py`**: Demonstrates how to unit test the `StorytellingAgent` in isolation by mocking its external dependencies (API calls) using `unittest.mock`.
    -   **`conftest.py`**: Shows how to create reusable test `fixtures` for `pytest`, resulting in cleaner and more maintainable tests.

Don't copy these examples directly, it is for a different project entirely. But use this as inspiration and for best practices.

### DOCUMENTATION:

-   **Project-Specific AI Guidelines:** For detailed implementation patterns and architectural decisions, you **must** refer to the **`AI_CODING_GUIDELINES.md`** file.
-   **Asynchronous I/O:** Core logic will heavily rely on Python's `asyncio` for non-blocking operations. [Python `asyncio` Documentation](https://docs.python.org/3/library/asyncio.html)
-   **System Services:** The application will be managed by `systemd`. Understanding `.service` files is crucial. [DigitalOcean `systemd` Essentials](https://www.digitalocean.com/community/tutorials/systemd-essentials-working-with-services-units-and-the-journal)
-   **Similar Projects:** My own almost complete but failed attempt: https://github.com/sarpel/storyteller-remote  and another users project: https://github.com/stefanom/fably

### OTHER CONSIDERATIONS:

-   **Environment Variables:** A `.env.example` file will be provided. All API keys and sensitive configurations **must** be managed via environment variables. **Do not hardcode keys in the source code.**
-   **Detailed README:** The `README.md` must include a project structure diagram and setup instructions covering software, API keys, and GPIO wiring.
-   **Critical Gotcha (Memory):** The application must **never** import or initiate more than one wakeword engine class at a time. The choice must be determined at startup from a configuration setting to conserve RAM.
-   **Gotcha: Hardware & OS Abstraction:** Do not write code that assumes a specific Raspberry Pi model or OS. All hardware-specific logic (GPIO pins, audio device names) must be handled through a configuration layer loaded based on the detected environment.
-   **Auto Start:** The application must be packaged to run as a `systemd` service (`storyteller.service`) for reliability and auto-restarts on failure.
-   **Auto Setup:** An automated `setup.sh` script is required to handle installation and configuration across different supported OS and hardware combinations.
-   **State Management:** To minimize dependencies, all application state (story library, schedules) **must** be stored in a lightweight **SQLite** database.
-   **Dependency Footprint:** Carefully consider every new dependency. The primary goal is to keep the application lean. Always check a library's resource usage before adding it.
-		**Possible Combinations:** Includes Raspberry Pi 5, Raspberry Pi Zero 2W as SBCs and Dietpi, Raspberry Pi OS as Operating Systems. If Rpi5 is the SBC then Waveshare usb to audio dongle will be set as arecord and play device, if it is rpi zero 2w then IQAudio Codec HAT will be the default for the same settings.