"""
Adapted from erp-managment/src/handler/errorHandler.py.

FIX #6 (was: `CustomError.__init__` called `super().__init__()` with NO
args, so `str(e)` was always `''` for any `CustomError` subclass --
breaking error diagnostics anywhere code does
`except Exception as e: ...str(e)`). Now forwards the resolved message to
`Exception.__init__` so `str(e)` works as expected.

The `backend_common.utils.exceptions` (CommonAccessDenied/CommonNotFound)
dependency is dropped here since it comes from the private `backend-common`
package that isn't reachable in this sandbox; register_errors() below
only wires the handlers that don't need it.
"""
import traceback

from flask import jsonify, Flask, make_response


class CustomError(Exception):
    def __init__(self, message=None, payload=None):
        self.message = message or self.get_default_message()
        super().__init__(self.message)  # FIX #6: was super().__init__() with no args
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        if self.message is not None:
            rv['error'] = self.message
        return rv

    def get_default_message(self):
        return None


class BadRequest(CustomError):
    status_code = 400


class ConflictRequest(CustomError):
    status_code = 409


class NotFound(CustomError):
    status_code = 404


class Unauthorized(CustomError):
    status_code = 401


class InvalidValue(CustomError):
    status_code = 400


class UnprocessableEntity(CustomError):
    status_code = 422


class InternalServer(CustomError):
    status_code = 500

    def get_default_message(self):
        return "Internal error, try again or see the Log"


class ExternalResourceFailed(CustomError):
    status_code = 408


def internal_error(e):
    print("Error: ", e)
    return {"error": "Internal error"}, 500


def customErrorListener(e):
    print("Custom error")
    return jsonify(e.to_dict()), e.status_code


def exceptionListener(e):
    print("Exception error")
    traceback.print_exc()
    return internal_error(e)


def not_found_error(e):
    print("404 error")
    return {"error": "Resource not found"}, 404


def register_errors(app: Flask):
    app.register_error_handler(404, not_found_error)
    app.register_error_handler(Exception, exceptionListener)
    app.register_error_handler(CustomError, customErrorListener)
