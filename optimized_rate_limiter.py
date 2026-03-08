
import logging

class DummyRateLimiter:
    def wait_if_needed(self, action_name):
        pass
    
    def record_prompt(self):
        pass

_instance = DummyRateLimiter()

def get_rate_limiter():
    return _instance
