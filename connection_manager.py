from enum import Enum, auto
import time
import logging
import threading
import random
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
import asyncio
from datetime import datetime, timedelta

# Configure logging with a higher level to reduce noise
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ConnectionManager')

class ConnectionState(Enum):
    """Enum representing possible connection states"""
    DISCONNECTED = auto()
    CONNECTING = auto()
    CONNECTED = auto()
    RECONNECTING = auto()
    FAILED = auto()
    SHUTTING_DOWN = auto()

@dataclass
class ConnectionConfig:
    """Configuration for connection management"""
    initial_timeout: float = 5.0  # Initial connection timeout in seconds
    max_retries: int = 5  # Maximum number of retry attempts
    base_retry_delay: float = 1.0  # Base delay for exponential backoff
    max_retry_delay: float = 30.0  # Maximum retry delay
    connection_check_interval: float = 1.0  # How often to check connection status
    keep_alive_interval: float = 30.0  # How often to send keep-alive packets

class ConnectionStateMachine:
    """Manages connection state and transitions with proper error handling and retry logic"""
    
    def __init__(self, 
                 config: ConnectionConfig,
                 on_state_change: Optional[Callable[[ConnectionState, ConnectionState], None]] = None,
                 on_connection_lost: Optional[Callable[[], None]] = None):
        self.config = config
        self._state = ConnectionState.DISCONNECTED
        self._state_lock = threading.Lock()
        self._operation_lock = threading.Lock()  # Lock for operations that should not be concurrent
        self._last_state_change = datetime.now()
        self._retry_count = 0
        self._last_retry_time = None
        self._connection_check_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._reconnect_timer: Optional[threading.Timer] = None
        
        # Callbacks
        self._on_state_change = on_state_change
        self._on_connection_lost = on_connection_lost
        
        # Connection monitoring
        self._last_activity = datetime.now()
        self._connection_healthy = False
        
        logger.info("ConnectionStateMachine initialized")

    @property
    def state(self) -> ConnectionState:
        """Thread-safe access to current state"""
        with self._state_lock:
            return self._state

    def _set_state(self, new_state: ConnectionState) -> bool:
        """Thread-safe state transition with validation"""
        with self._state_lock:
            old_state = self._state
            if self._is_valid_transition(old_state, new_state):
                self._state = new_state
                self._last_state_change = datetime.now()
                logger.info(f"State transition: {old_state} -> {new_state}")
                if self._on_state_change:
                    try:
                        self._on_state_change(old_state, new_state)
                    except Exception as e:
                        logger.error(f"Error in state change callback: {e}")
                return True
            else:
                logger.debug(f"Invalid state transition attempted: {old_state} -> {new_state}")
                return False

    def _is_valid_transition(self, old_state: ConnectionState, new_state: ConnectionState) -> bool:
        """Validate state transitions"""
        valid_transitions = {
            ConnectionState.DISCONNECTED: {ConnectionState.CONNECTING, ConnectionState.SHUTTING_DOWN},
            ConnectionState.CONNECTING: {ConnectionState.CONNECTED, ConnectionState.FAILED, ConnectionState.SHUTTING_DOWN, ConnectionState.DISCONNECTED},
            ConnectionState.CONNECTED: {ConnectionState.RECONNECTING, ConnectionState.DISCONNECTED, ConnectionState.SHUTTING_DOWN},
            ConnectionState.RECONNECTING: {ConnectionState.CONNECTED, ConnectionState.FAILED, ConnectionState.SHUTTING_DOWN, ConnectionState.DISCONNECTED},
            ConnectionState.FAILED: {ConnectionState.RECONNECTING, ConnectionState.DISCONNECTED, ConnectionState.SHUTTING_DOWN},
            ConnectionState.SHUTTING_DOWN: {ConnectionState.DISCONNECTED}
        }
        return new_state in valid_transitions.get(old_state, set())

    def start_connection(self) -> None:
        """Start the connection process"""
        with self._operation_lock:
            if self.state == ConnectionState.DISCONNECTED:
                if self._set_state(ConnectionState.CONNECTING):
                    self._retry_count = 0
                    self._start_connection_monitor()
            else:
                logger.debug(f"Cannot start connection in state: {self.state}")

    def connection_succeeded(self) -> None:
        """Handle successful connection"""
        with self._operation_lock:
            current_state = self.state
            if current_state in {ConnectionState.CONNECTING, ConnectionState.RECONNECTING}:
                if self._set_state(ConnectionState.CONNECTED):
                    self._retry_count = 0
                    self._connection_healthy = True
                    self._last_activity = datetime.now()
                    if self._reconnect_timer:
                        self._reconnect_timer.cancel()
                        self._reconnect_timer = None
            else:
                logger.debug(f"Unexpected connection success in state: {current_state}")

    def connection_failed(self, error: Optional[Exception] = None) -> None:
        """Handle connection failure"""
        with self._operation_lock:
            current_state = self.state
            if current_state in {ConnectionState.CONNECTING, ConnectionState.RECONNECTING}:
                self._retry_count += 1
                if self._retry_count >= self.config.max_retries:
                    if self._set_state(ConnectionState.FAILED):
                        logger.error(f"Connection failed after {self._retry_count} attempts. Last error: {error}")
                else:
                    delay = self._calculate_retry_delay()
                    logger.info(f"Connection attempt {self._retry_count}/{self.config.max_retries} failed. Retrying in {delay:.1f}s. Error: {error}")
                    if self._set_state(ConnectionState.RECONNECTING):
                        self._schedule_reconnect(delay)
            else:
                logger.debug(f"Unexpected connection failure in state: {current_state}")

    def _calculate_retry_delay(self) -> float:
        """Calculate exponential backoff delay with jitter"""
        delay = min(
            self.config.base_retry_delay * (2 ** self._retry_count),
            self.config.max_retry_delay
        )
        # Add jitter (±20%)
        jitter = delay * 0.2
        return delay + (random.random() * 2 - 1) * jitter

    def _schedule_reconnect(self, delay: float) -> None:
        """Schedule a reconnection attempt"""
        def reconnect():
            if not self._stop_event.is_set():
                with self._operation_lock:
                    if self.state in {ConnectionState.RECONNECTING, ConnectionState.FAILED}:
                        self._set_state(ConnectionState.CONNECTING)
        
        if self._reconnect_timer:
            self._reconnect_timer.cancel()
        
        self._last_retry_time = datetime.now()
        self._reconnect_timer = threading.Timer(delay, reconnect)
        self._reconnect_timer.daemon = True
        self._reconnect_timer.start()

    def _start_connection_monitor(self) -> None:
        """Start the connection monitoring thread"""
        if self._connection_check_thread is None or not self._connection_check_thread.is_alive():
            self._stop_event.clear()
            self._connection_check_thread = threading.Thread(
                target=self._connection_monitor_loop,
                daemon=True
            )
            self._connection_check_thread.start()

    def _connection_monitor_loop(self) -> None:
        """Monitor connection health and handle reconnection"""
        consecutive_failures = 0
        while not self._stop_event.is_set():
            try:
                current_state = self.state
                if current_state == ConnectionState.CONNECTED:
                    # Check connection health
                    if not self._connection_healthy:
                        consecutive_failures += 1
                        logger.debug(f"Connection health check failed (attempt {consecutive_failures})")
                        if consecutive_failures >= 3:  # Require multiple failures before reconnecting
                            logger.warning("Multiple connection health checks failed, initiating reconnection")
                            with self._operation_lock:
                                if self.state == ConnectionState.CONNECTED:
                                    self._set_state(ConnectionState.RECONNECTING)
                                    self.connection_failed()
                            consecutive_failures = 0
                    else:
                        # Reset health flag and failure counter for next check
                        self._connection_healthy = False
                        consecutive_failures = 0
                        logger.debug("Connection health check passed")
                
                time.sleep(self.config.connection_check_interval)
            except Exception as e:
                logger.error(f"Error in connection monitor: {e}")
                consecutive_failures = 0  # Reset on error
                time.sleep(1.0)  # Prevent tight loop on error

    def update_activity(self) -> None:
        """Update last activity timestamp and connection health"""
        self._last_activity = datetime.now()
        self._connection_healthy = True
        logger.debug("Connection activity updated")

    def shutdown(self) -> None:
        """Gracefully shutdown the connection manager"""
        logger.info("Initiating connection manager shutdown")
        self._stop_event.set()
        
        if self._reconnect_timer:
            self._reconnect_timer.cancel()
            self._reconnect_timer = None
        
        with self._operation_lock:
            self._set_state(ConnectionState.SHUTTING_DOWN)
        
        if self._connection_check_thread and self._connection_check_thread.is_alive():
            self._connection_check_thread.join(timeout=5.0)
        
        self._set_state(ConnectionState.DISCONNECTED)
        logger.info("Connection manager shutdown complete")

    def get_connection_status(self) -> Dict[str, Any]:
        """Get detailed connection status"""
        with self._state_lock:
            return {
                "state": self.state.name,
                "retry_count": self._retry_count,
                "last_state_change": self._last_state_change.isoformat(),
                "last_activity": self._last_activity.isoformat(),
                "connection_healthy": self._connection_healthy,
                "time_since_last_activity": (datetime.now() - self._last_activity).total_seconds(),
                "time_in_current_state": (datetime.now() - self._last_state_change).total_seconds()
            } 