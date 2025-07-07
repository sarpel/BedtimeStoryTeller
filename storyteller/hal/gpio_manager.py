"""
GPIO management for button inputs and LED outputs.
Provides hardware abstraction for GPIO operations on Raspberry Pi.
"""

import asyncio
import logging
import threading
import time
from typing import Dict, Any, Callable, Optional
from .interface import GPIOInterface, PinMode, PinState, ButtonEvent

logger = logging.getLogger(__name__)


class RPiGPIOManager(GPIOInterface):
    """Raspberry Pi GPIO manager using RPi.GPIO library."""
    
    def __init__(self):
        super().__init__()
        self.GPIO = None
        self._setup_pins: Dict[int, PinMode] = {}
        self._button_handlers: Dict[int, threading.Thread] = {}
        self._led_states: Dict[int, bool] = {}
        self._shutdown_event = threading.Event()
    
    async def initialize(self) -> None:
        """Initialize GPIO interface."""
        try:
            # Import RPi.GPIO only when needed
            try:
                import RPi.GPIO as GPIO
                self.GPIO = GPIO
            except ImportError:
                raise ImportError("RPi.GPIO not available. Install with: pip install RPi.GPIO")
            
            logger.info("Initializing RPi.GPIO...")
            
            # Set GPIO mode to BCM
            self.GPIO.setmode(self.GPIO.BCM)
            
            # Disable warnings about already configured pins
            self.GPIO.setwarnings(False)
            
            self.is_initialized = True
            logger.info("RPi.GPIO initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize GPIO: {e}")
            raise
    
    async def cleanup(self) -> None:
        """Clean up GPIO resources."""
        logger.info("Cleaning up GPIO...")
        
        # Signal shutdown to all threads
        self._shutdown_event.set()
        
        # Wait for button handler threads to finish
        for thread in self._button_handlers.values():
            if thread.is_alive():
                thread.join(timeout=1.0)
        
        self._button_handlers.clear()
        
        # Turn off all LEDs
        for pin, state in self._led_states.items():
            if state:
                try:
                    await self.set_led(pin, False)
                except:
                    pass
        
        # Clean up GPIO
        if self.GPIO:
            self.GPIO.cleanup()
        
        self.is_initialized = False
        logger.info("GPIO cleanup completed")
    
    async def setup_pin(self, pin: int, mode: PinMode) -> None:
        """Setup a GPIO pin."""
        if not self.is_initialized:
            raise RuntimeError("GPIO not initialized")
        
        try:
            if mode == PinMode.OUTPUT:
                self.GPIO.setup(pin, self.GPIO.OUT)
            elif mode == PinMode.INPUT:
                self.GPIO.setup(pin, self.GPIO.IN)
            elif mode == PinMode.INPUT_PULLUP:
                self.GPIO.setup(pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_UP)
            elif mode == PinMode.INPUT_PULLDOWN:
                self.GPIO.setup(pin, self.GPIO.IN, pull_up_down=self.GPIO.PUD_DOWN)
            
            self._setup_pins[pin] = mode
            logger.debug(f"Setup GPIO pin {pin} as {mode.value}")
            
        except Exception as e:
            logger.error(f"Failed to setup pin {pin}: {e}")
            raise
    
    async def read_pin(self, pin: int) -> PinState:
        """Read the state of a GPIO pin."""
        if not self.is_initialized:
            raise RuntimeError("GPIO not initialized")
        
        if pin not in self._setup_pins:
            raise ValueError(f"Pin {pin} not setup")
        
        try:
            value = self.GPIO.input(pin)
            return PinState.HIGH if value else PinState.LOW
        except Exception as e:
            logger.error(f"Failed to read pin {pin}: {e}")
            raise
    
    async def write_pin(self, pin: int, state: PinState) -> None:
        """Write to a GPIO pin."""
        if not self.is_initialized:
            raise RuntimeError("GPIO not initialized")
        
        if pin not in self._setup_pins:
            raise ValueError(f"Pin {pin} not setup")
        
        if self._setup_pins[pin] != PinMode.OUTPUT:
            raise ValueError(f"Pin {pin} not configured as output")
        
        try:
            self.GPIO.output(pin, state.value)
            logger.debug(f"Set GPIO pin {pin} to {state.name}")
        except Exception as e:
            logger.error(f"Failed to write pin {pin}: {e}")
            raise
    
    async def setup_button(
        self, 
        pin: int, 
        callback: Callable[[ButtonEvent], None],
        pull_up: bool = True,
        bounce_time: int = 200
    ) -> None:
        """Setup a button with interrupt handling."""
        if not self.is_initialized:
            raise RuntimeError("GPIO not initialized")
        
        try:
            # Setup pin as input with pull-up/down
            mode = PinMode.INPUT_PULLUP if pull_up else PinMode.INPUT_PULLDOWN
            await self.setup_pin(pin, mode)
            
            # Store callback
            self._button_callbacks[pin] = callback
            
            # Start button monitoring thread
            handler_thread = threading.Thread(
                target=self._button_handler,
                args=(pin, callback, pull_up, bounce_time),
                daemon=True
            )
            handler_thread.start()
            self._button_handlers[pin] = handler_thread
            
            logger.info(f"Setup button on GPIO pin {pin}")
            
        except Exception as e:
            logger.error(f"Failed to setup button on pin {pin}: {e}")
            raise
    
    def _button_handler(
        self, 
        pin: int, 
        callback: Callable[[ButtonEvent], None], 
        pull_up: bool, 
        bounce_time: int
    ) -> None:
        """Button monitoring thread."""
        try:
            last_state = self.GPIO.input(pin)
            last_change_time = time.time()
            press_start_time = None
            
            while not self._shutdown_event.is_set():
                current_state = self.GPIO.input(pin)
                current_time = time.time()
                
                # Check for state change
                if current_state != last_state:
                    # Debounce check
                    if (current_time - last_change_time) * 1000 >= bounce_time:
                        # Determine if this is a press or release
                        if pull_up:
                            # With pull-up: pressed = LOW, released = HIGH
                            pressed = (current_state == 0)
                        else:
                            # With pull-down: pressed = HIGH, released = LOW
                            pressed = (current_state == 1)
                        
                        if pressed:
                            # Button pressed
                            press_start_time = current_time
                            event = ButtonEvent(
                                pin=pin,
                                state=PinState.LOW if pull_up else PinState.HIGH,
                                timestamp=current_time
                            )
                            callback(event)
                            
                        else:
                            # Button released
                            duration = None
                            if press_start_time:
                                duration = current_time - press_start_time
                            
                            event = ButtonEvent(
                                pin=pin,
                                state=PinState.HIGH if pull_up else PinState.LOW,
                                timestamp=current_time,
                                duration=duration
                            )
                            callback(event)
                            press_start_time = None
                        
                        last_change_time = current_time
                    
                    last_state = current_state
                
                time.sleep(0.01)  # 10ms polling interval
                
        except Exception as e:
            logger.error(f"Button handler error on pin {pin}: {e}")
    
    async def setup_led(self, pin: int) -> None:
        """Setup an LED pin."""
        await self.setup_pin(pin, PinMode.OUTPUT)
        self._led_states[pin] = False
        await self.set_led(pin, False)  # Start with LED off
        logger.info(f"Setup LED on GPIO pin {pin}")
    
    async def set_led(self, pin: int, state: bool) -> None:
        """Set LED state."""
        if pin not in self._led_states:
            raise ValueError(f"LED on pin {pin} not setup")
        
        pin_state = PinState.HIGH if state else PinState.LOW
        await self.write_pin(pin, pin_state)
        self._led_states[pin] = state
        logger.debug(f"Set LED on pin {pin} to {'ON' if state else 'OFF'}")
    
    async def blink_led(self, pin: int, duration: float = 0.5, count: int = 1) -> None:
        """Blink an LED."""
        if pin not in self._led_states:
            raise ValueError(f"LED on pin {pin} not setup")
        
        original_state = self._led_states[pin]
        
        try:
            for _ in range(count):
                # Turn on
                await self.set_led(pin, True)
                await asyncio.sleep(duration / 2)
                
                # Turn off
                await self.set_led(pin, False)
                await asyncio.sleep(duration / 2)
            
            # Restore original state
            await self.set_led(pin, original_state)
            
        except Exception as e:
            logger.error(f"LED blink error on pin {pin}: {e}")
            # Try to restore original state
            try:
                await self.set_led(pin, original_state)
            except:
                pass
            raise
    
    def is_available(self) -> bool:
        """Check if GPIO interface is available."""
        try:
            import RPi.GPIO
            return True
        except ImportError:
            return False
    
    def get_gpio_info(self) -> Dict[str, Any]:
        """Get GPIO information."""
        return {
            "type": "rpi_gpio",
            "initialized": self.is_initialized,
            "setup_pins": {pin: mode.value for pin, mode in self._setup_pins.items()},
            "button_pins": list(self._button_callbacks.keys()),
            "led_pins": list(self._led_states.keys()),
            "led_states": self._led_states.copy()
        }


class MockGPIOManager(GPIOInterface):
    """Mock GPIO manager for testing and development."""
    
    def __init__(self):
        super().__init__()
        self._setup_pins: Dict[int, PinMode] = {}
        self._pin_states: Dict[int, PinState] = {}
        self._led_states: Dict[int, bool] = {}
    
    async def initialize(self) -> None:
        """Initialize mock GPIO."""
        logger.info("Initializing mock GPIO...")
        self.is_initialized = True
        logger.info("Mock GPIO ready")
    
    async def cleanup(self) -> None:
        """Clean up mock GPIO."""
        logger.info("Mock GPIO cleanup")
        self.is_initialized = False
    
    async def setup_pin(self, pin: int, mode: PinMode) -> None:
        """Setup a mock GPIO pin."""
        self._setup_pins[pin] = mode
        if mode == PinMode.INPUT_PULLUP:
            self._pin_states[pin] = PinState.HIGH
        elif mode == PinMode.INPUT_PULLDOWN:
            self._pin_states[pin] = PinState.LOW
        else:
            self._pin_states[pin] = PinState.LOW
        
        logger.info(f"Mock: Setup pin {pin} as {mode.value}")
    
    async def read_pin(self, pin: int) -> PinState:
        """Read mock pin state."""
        if pin not in self._setup_pins:
            raise ValueError(f"Pin {pin} not setup")
        
        return self._pin_states.get(pin, PinState.LOW)
    
    async def write_pin(self, pin: int, state: PinState) -> None:
        """Write to mock pin."""
        if pin not in self._setup_pins:
            raise ValueError(f"Pin {pin} not setup")
        
        if self._setup_pins[pin] != PinMode.OUTPUT:
            raise ValueError(f"Pin {pin} not configured as output")
        
        self._pin_states[pin] = state
        logger.info(f"Mock: Set pin {pin} to {state.name}")
    
    async def setup_button(
        self, 
        pin: int, 
        callback: Callable[[ButtonEvent], None],
        pull_up: bool = True,
        bounce_time: int = 200
    ) -> None:
        """Setup mock button."""
        mode = PinMode.INPUT_PULLUP if pull_up else PinMode.INPUT_PULLDOWN
        await self.setup_pin(pin, mode)
        self._button_callbacks[pin] = callback
        logger.info(f"Mock: Setup button on pin {pin}")
    
    async def setup_led(self, pin: int) -> None:
        """Setup mock LED."""
        await self.setup_pin(pin, PinMode.OUTPUT)
        self._led_states[pin] = False
        logger.info(f"Mock: Setup LED on pin {pin}")
    
    async def set_led(self, pin: int, state: bool) -> None:
        """Set mock LED state."""
        if pin not in self._led_states:
            raise ValueError(f"LED on pin {pin} not setup")
        
        self._led_states[pin] = state
        pin_state = PinState.HIGH if state else PinState.LOW
        await self.write_pin(pin, pin_state)
        logger.info(f"Mock: Set LED on pin {pin} to {'ON' if state else 'OFF'}")
    
    async def blink_led(self, pin: int, duration: float = 0.5, count: int = 1) -> None:
        """Blink mock LED."""
        logger.info(f"Mock: Blinking LED on pin {pin} {count} times (duration: {duration}s)")
        
        original_state = self._led_states.get(pin, False)
        
        for i in range(count):
            await self.set_led(pin, True)
            await asyncio.sleep(duration / 2)
            await self.set_led(pin, False)
            await asyncio.sleep(duration / 2)
        
        # Restore original state
        await self.set_led(pin, original_state)
    
    def is_available(self) -> bool:
        """Mock GPIO is always available."""
        return True
    
    async def simulate_button_press(self, pin: int, duration: float = 0.1) -> None:
        """Simulate a button press for testing."""
        if pin not in self._button_callbacks:
            logger.warning(f"No button callback for pin {pin}")
            return
        
        callback = self._button_callbacks[pin]
        current_time = time.time()
        
        # Simulate press
        press_event = ButtonEvent(
            pin=pin,
            state=PinState.LOW,  # Assuming pull-up configuration
            timestamp=current_time
        )
        callback(press_event)
        
        # Wait for duration
        await asyncio.sleep(duration)
        
        # Simulate release
        release_event = ButtonEvent(
            pin=pin,
            state=PinState.HIGH,
            timestamp=current_time + duration,
            duration=duration
        )
        callback(release_event)
        
        logger.info(f"Mock: Simulated button press on pin {pin} (duration: {duration}s)")


async def create_gpio_manager() -> GPIOInterface:
    """
    Create appropriate GPIO manager based on hardware availability.
    
    Returns:
        GPIOInterface: GPIO manager instance
    """
    # Try to detect if we're on a Raspberry Pi
    try:
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read().lower()
            if 'raspberry pi' in model:
                logger.info("Detected Raspberry Pi, using RPi.GPIO")
                return RPiGPIOManager()
    except:
        pass
    
    # Check if RPi.GPIO is available
    try:
        import RPi.GPIO
        logger.info("RPi.GPIO available, using real GPIO")
        return RPiGPIOManager()
    except ImportError:
        logger.info("RPi.GPIO not available, using mock GPIO")
        return MockGPIOManager()