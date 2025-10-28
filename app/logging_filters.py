import logging

class IPAddressFilter(logging.Filter):
    """
    Add client IP address to log records
    """
    def filter(self, record):
        # This will be set in the view before logging
        if not hasattr(record, 'ip'):
            record.ip = 'unknown'
        return True
