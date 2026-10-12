# ui/helpers.py
# -*- coding: utf-8 -*-
import logging
import traceback

def log_error(message: str):
    logging.error(f"{message}\n{traceback.format_exc()}")
