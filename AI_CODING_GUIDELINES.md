# Master AI Coding Guidelines: Bedtime Storyteller Gadget

This document is the **single source of truth** for all technical development. You, as the AI assistant, **must** adhere to these principles and patterns to ensure the final product is robust, maintainable,and meets its strict resource constraints.

## 1. Guiding Philosophy: Resource-First Development

Our number one priority is **performance on a resource-constrained device** (Raspberry Pi Zero 2W). Every line of code, every chosen dependency, and every architectural decision must be weighed against its impact on RAM (~350-400MB target) and CPU usage.

**Think lean. Think efficient. Think non-blocking.**

## 2. Core Architectural Patterns (Non-Negotiable)

### 2.1. Asynchronous-First Imperative
The entire application **must** be built on Python's `asyncio` framework to handle concurrent I/O without blocking.

-   All I/O-bound operations (network calls, database access, hardware interaction) **must** use `async/await`.
-   **Prohibited:** Do not use blocking libraries like `requests`. Use `httpx.AsyncClient`.
-   **For Blocking SDKs:** If a necessary library does not support `asyncio`, it **must** be wrapped and run in a separate thread pool using `loop.run_in_executor()` to avoid blocking the main event loop.

    ```python
    # Example of wrapping a blocking call
    import time
    import asyncio

    def blocking_sync_function():
        time.sleep(2) # Represents a blocking I/O call
        return "Done"

    async def main():
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, blocking_sync_function)
        print(result)
    ```

### 2.2. The Agent & Provider Pattern
All external services (LLM, TTS, STT) **must** be abstracted using a `Provider` pattern. This decouples the core logic from specific implementations, allowing for runtime switching and simplified testing.

```python
# storyteller/providers/base.py
from abc import ABC, abstractmethod

class BaseLlmProvider(ABC):
    @abstractmethod
    async def generate_story_stream(self, prompt: str): # -> AsyncGenerator[str, None]
        """Streams a story paragraph by paragraph."""
        pass

# storyteller/agent.py
from storyteller.providers.base import BaseLlmProvider

class StorytellingAgent:
    def __init__(self, llm_provider: BaseLlmProvider):
        self._llm = llm_provider
```

### 2.3. The Paragraph-Based Streaming Pipeline
The core story generation loop must stream paragraphs from the LLM and concurrently process them for TTS and playback. This is **critical** for minimizing time-to-first-sound.

```python
# Conceptual Agent Logic
async def tell_story(self, prompt: str):
    playback_queue = asyncio.Queue()
    tts_tasks = []
    playback_task = asyncio.create_task(self.audio_player.play_from_queue(playback_queue))

    async for paragraph in self._llm.generate_story_stream(prompt):
        task = asyncio.create_task(
            self._tts.synthesize_and_queue(paragraph, playback_queue)
        )
        tts_tasks.append(task)

    await asyncio.gather(*tts_tasks)
    await playback_queue.join()
    await playback_task
```

## 3. Critical Resource Management

-   **Memory Ceiling:** Total application RAM usage **must not exceed 400MB**.
-   **Dynamic Wakeword Loading:** To conserve memory, **never** statically import multiple wakeword engines. Use `importlib` to load only the configured engine's module at runtime.

    ```python
    # storyteller/wakeword/loader.py
    import importlib

    def load_wakeword_engine(config: dict):
        engine_name = config['engine_name'] # e.g., "porcupine"
        module_path = f"storyteller.wakeword.{engine_name}_engine"
        try:
            engine_module = importlib.import_module(module_path)
            return engine_module.create_engine(config)
        except (ImportError, AttributeError) as e:
            raise ValueError(f"Could not load wakeword engine: {engine_name}") from e
    ```
-   **Lean Dependencies:** Every new third-party dependency must be justified and analyzed for its resource footprint.

## 4. Hardware Abstraction Layer (HAL)

-   **No Hardcoding:** Absolutely no hardcoded GPIO pin numbers, audio device names, or other hardware-specific values in the application logic.
-   **Bridge Pattern:** The HAL must use a Bridge pattern. Define abstract interfaces (e.g., `AudioInterface`), then create concrete implementations for each hardware configuration (`USBAudioDevice`, `MockedDevice`). The application is instantiated with the appropriate implementation at runtime.

## 5. State Management & Data Schemas

-   **Local State (SQLite):** All application state (story library, settings, schedules) **must** be stored in a single SQLite database file, accessed via the built-in `sqlite3` library.
-   **Long-Term Memory (Qdrant):** The schema for the `conversational_memory` collection is defined as follows:

| Field Name | Data Type | Indexing | Description |
| :--- | :--- | :--- | :--- |
| `id` | UUID | Indexed | Unique identifier for the point. |
| `vector` | Float Vector | HNSW | Embedding of the `text` field. |
| `payload.session_id`| Keyword | Indexed | ID for a single continuous user interaction.|
| `payload.speaker` | Keyword | Indexed | "user" or "bot". |
| `payload.text` | Text | Full Text | The raw text content of the utterance. |
| `payload.timestamp`| Datetime | Indexed | ISO 8601 timestamp of the event. |

## 6. Code Quality & Standards

-   **Type Hinting:** All function signatures and class member variables **must** include full type hints. This is not optional.
-   **Logging:** Use Python's built-in `logging` module for all diagnostic output. **Do not use `print()`** in application code.
-   **Error Handling:** Use specific `try...except` blocks for all I/O. The system must gracefully handle API failures.
-   **Security:** All secrets (API keys) **must** be loaded from environment variables (`.env` file). Never hardcode credentials.

## 7. Testing Strategy

-   **Framework:** Use `pytest` for all tests.
-   **Unit Tests:** Isolate and test individual components. External services **must** be mocked using `unittest.mock` and `AsyncMock`.
-   **No Network in Tests:** Tests must not make real network requests.
-   **HAL Mocking:** The HAL's `MockedDevice` implementation is crucial for testing the full application pipeline in a CI/CD environment without physical hardware.