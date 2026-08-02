"""
Adapted from erp-managment/src/handler/requestHandler.py.

FIX #2 (was: `timeout` defaulted to `None`, i.e. no timeout at all on the
outbound `requests.request(...)` call). Combined with the (also now
fixed, see src/config/__init__.py) missing Celery task_time_limit, a
hung/slow HTTP dependency could block a worker slot forever with zero
log output. Now defaults to `settings.DEFAULT_HTTP_TIMEOUT_SECONDS`
instead of `None`, so a call that gets no response within that window
raises `requests.exceptions.Timeout` instead of hanging indefinitely.
See scripts/demo_bugs.sh part 2 for the before/after.
"""
import datetime
import json as js
import time
from uuid import uuid4

import requests
from flask import request, has_request_context

from src.config import settings

logger = settings.logger

SECRET_VALUES = [
    "password",
    "secret",
    "token",
    "authorization",
    "bearer",
]


class RequestHadnler:
    @staticmethod
    def handle_request(url, headers=None, data=None, json=None, params=None,
                        method="GET", tag="", stream=False, retry_count: int = 0,
                        timeout=None):
        # FIX #2: `timeout=None` used to mean "no timeout" every time a
        # caller didn't pass one explicitly. Now fall back to a bounded
        # default instead of blocking forever.
        if timeout is None:
            timeout = settings.DEFAULT_HTTP_TIMEOUT_SECONDS
        RequestHadnler.__inject_correlation_id(headers)
        endpoint = "/".join(url.split("/")[3:])
        log_obj = {
            "timestamp": datetime.datetime.now().isoformat(),
            "service": "erp-celery-poc",
            "headers": RequestHadnler.sanitize_data(headers),
            "data": RequestHadnler.sanitize_data(data),
            "json": RequestHadnler.sanitize_data(json),
            "params": RequestHadnler.sanitize_data(params),
            "url": url,
            "endpoint": endpoint,
            "method": method,
            "tag": tag,
        }
        start_time = time.time()
        logger.debug("starting request")
        res = requests.request(method, url, headers=headers, data=data, json=json,
                                params=params, stream=stream, timeout=timeout)
        log_obj.update(
            {
                "status_code": res.status_code,
                "response_body": "[STREAMING RESPONSE]" if stream else res.text,
                "response_header": dict(res.headers),
                "response_time": f'{int((time.time() - start_time) * 1000)} ms',
            }
        )
        try:
            res.raise_for_status()
        except Exception as err:
            log_obj["error"] = str(err)
            if retry_count > 0:
                time.sleep(.01)  # 10ms delay before retry
                return RequestHadnler.handle_request(url, headers, data, json, params,
                                                      method, tag, stream, retry_count - 1, timeout)
        logger.debug(js.dumps(log_obj, indent=2))
        return res

    @staticmethod
    def __inject_correlation_id(headers):
        if has_request_context():
            correlation_id = request.headers.get('X-Correlation-ID', str(uuid4()))
        else:
            correlation_id = str(uuid4())

        if headers is not None:
            headers['X-Correlation-ID'] = correlation_id

    @staticmethod
    def sanitize_data(data):
        if isinstance(data, dict):
            return {
                k: (
                    "***"
                    if any(secret in k.lower() for secret in SECRET_VALUES)
                    else RequestHadnler.sanitize_data(v)
                )
                for k, v in data.items()
            }
        return data


handle_request = RequestHadnler.handle_request
