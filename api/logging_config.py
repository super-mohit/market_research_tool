# File: api/logging_config.py (NEW FILE)
import logging
import sys

def setup_logging():
    """
    Configures logging for the application to output structured logs to stdout.
    """
    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO) # Set the minimum level of logs to capture

    # Remove any existing handlers to avoid duplicate logs
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # Create a handler to write to standard output (console)
    handler = logging.StreamHandler(sys.stdout)
    
    # Create a formatter that outputs logs in a structured, readable format
    # We include timestamp, log level, logger name, and the message.
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s'
    )
    handler.setFormatter(formatter)

    # Add the handler to the root logger
    root_logger.addHandler(handler)

    # Set the logging level for libraries that are too verbose
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    # Log a confirmation message
    logging.info("Logging configured successfully.") 