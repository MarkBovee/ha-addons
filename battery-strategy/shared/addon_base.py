"""Base framework for Home Assistant add-ons.

This module provides common functionality for graceful shutdown,
logging setup, and main loop patterns used across all add-ons.

Usage:
    from shared.addon_base import setup_logging, setup_signal_handlers, sleep_with_shutdown_check

    setup_logging()
    shutdown_flag = setup_signal_handlers()
    
    while not shutdown_flag.is_set():
        do_work()
        if not sleep_with_shutdown_check(shutdown_flag, interval_seconds):
            break
"""

import logging
import signal
import time
import threading
from typing import Callable, Optional


def setup_logging(level: int = logging.INFO, name: Optional[str] = None) -> logging.Logger:
    """Configure standard logging format for add-ons.
    
    Args:
        level: Logging level (default: INFO)
        name: Logger name (default: None for root logger)
        
    Returns:
        Configured logger instance
    """
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    return logging.getLogger(name)


def setup_signal_handlers(logger: Optional[logging.Logger] = None) -> threading.Event:
    """Register SIGTERM and SIGINT handlers for graceful shutdown.
    
    Args:
        logger: Optional logger for shutdown messages
        
    Returns:
        Event that will be set when shutdown signal is received
    """
    shutdown_event = threading.Event()
    _logger = logger or logging.getLogger(__name__)
    
    def signal_handler(signum, frame):
        _logger.info("Received signal %d, initiating graceful shutdown...", signum)
        shutdown_event.set()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    return shutdown_event


def sleep_with_shutdown_check(
    shutdown_event: threading.Event, 
    total_seconds: int,
    check_interval: int = 1
) -> bool:
    """Sleep for specified duration while checking for shutdown signal.
    
    Args:
        shutdown_event: Event to check for shutdown
        total_seconds: Total time to sleep in seconds
        check_interval: How often to check for shutdown (default: 1 second)
        
    Returns:
        True if sleep completed normally, False if shutdown was requested
    """
    for _ in range(0, total_seconds, check_interval):
        if shutdown_event.is_set():
            return False
        time.sleep(min(check_interval, total_seconds))
    return not shutdown_event.is_set()


def run_addon_loop(
    update_func: Callable[[], None],
    interval_seconds: int,
    shutdown_event: threading.Event,
    logger: Optional[logging.Logger] = None,
    run_once: bool = False
) -> None:
    """Run main add-on loop with graceful shutdown support.
    
    Args:
        update_func: Function to call each iteration
        interval_seconds: Sleep interval between iterations
        shutdown_event: Event to check for shutdown
        logger: Optional logger for error messages
        run_once: If True, exit after first iteration
    """
    _logger = logger or logging.getLogger(__name__)
    
    while not shutdown_event.is_set():
        try:
            update_func()
        except Exception as e:
            _logger.error("Error in update loop: %s", e, exc_info=True)
        
        if run_once:
            _logger.info("Single iteration complete, exiting")
            break
        
        if not sleep_with_shutdown_check(shutdown_event, interval_seconds):
            break
