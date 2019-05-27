"""Routes and main logic for the migration service"""

import time
import logging

import flask
from werkzeug.exceptions import HTTPException

from . import errors as MigrationErrors
from .init import app, statsd, main_account, redis_conn, cache
from .config import KIN_ISSUER, DEBUG
from .helpers import is_burned, get_kin2_account_data
from . import migration


logger = logging.getLogger('migration')
HTTP_STATUS_OK = 200
HTTP_STATUS_INTERNAL_ERROR = 500


@app.before_request
def set_start_time():
    # Add starting time
    flask.g.start_time = time.time()


@app.route('/accounts/<account_address>/status', methods=['GET'])
def account_status(account_address):
    logger.info(f'Received an account status request for address: {account_address}')

    kin2_account_data = get_kin2_account_data(account_address)
    return flask.jsonify({
        'is_burned': is_burned(kin2_account_data)
    }), HTTP_STATUS_OK


@app.route('/migrate', methods=['POST'])
def migrate():
    account_address = flask.request.args.get('address', '')
    logger.info(f'Received migration request for address: {account_address}')

    with redis_conn.lock(f'migrating:{account_address}', blocking_timeout=30):
        # will throw LockError when failing to lock within blocking_timeout
        if cache.is_migrated(account_address):
            raise MigrationErrors.AlreadyMigratedError(account_address)
        migrated_balance = migration.migrate(account_address)
        cache.set_migrated(account_address)

    return flask.jsonify({'code': HTTP_STATUS_OK, 'message': 'OK', 'balance': migrated_balance }), HTTP_STATUS_OK


@app.route('/status', methods=['GET'])
def status():
    logger.info(f'Received status request')
    account_status = main_account.get_status()['account']
    account_status['old_kin_issuer'] = KIN_ISSUER
    statsd.gauge('wallet_balance', account_status['balance'])
    statsd.gauge('total_channels', account_status['channels']['total_channels'])
    statsd.gauge('free_channels', account_status['channels']['free_channels'])
    return flask.jsonify(account_status), HTTP_STATUS_OK


@app.after_request
def log_and_report_metrics(response):
    # Log request response time
    response_time = time.time() - flask.g.start_time
    path = flask.request.url_rule.rule if flask.request.url_rule else '404'
    statsd.histogram('response_time', response_time, tags=[f'path:{path}'])
    logger.info(f'Finished handling request after {response_time} seconds')
    return response


@app.errorhandler(MigrationErrors.MigrationError)
def migration_error_handle(exception: MigrationErrors.MigrationError):
    # If it is one of our custom errors, log and report it to statsd
    statsd.increment(exception.statsd_metric)
    logger.error(exception.error)
    return flask.jsonify(exception.to_dict()), exception.http_code


@app.errorhandler(HTTPException)
def http_error_handler(exception: HTTPException):
    logger.exception(f'Http exception: {repr(exception)}')
    return flask.jsonify({'code': exception.code, 'message': exception.__str__()}), exception.code


@app.errorhandler(Exception)
def error_handle(exception: Exception):
    # Log the exception and return an internal server error
    logger.exception(f'Unexpected exception: {str(exception)}')
    return flask.jsonify(MigrationErrors.InternalError().to_dict()), HTTP_STATUS_INTERNAL_ERROR


if __name__ == '__main__':
    if DEBUG:
        app.run('0.0.0.0', port=8000)
