"""Routes and main logic for the migration service"""

import time
import logging

import flask
import requests
from werkzeug.exceptions import HTTPException

import kin.errors as KinErrors
from kin.transactions import build_memo

from . import errors as MigrationErrors
from .init import app, statsd, main_account
from .config import KIN_ISSUER, DEBUG, PROXY_SALT, APP_INTERNAL_SERVICE
from .helpers import (get_proxy_address,
                      get_old_balance,
                      sign_tx,
                      build_migration_transaction,
                      build_create_transaction,
                      is_burned, get_kin2_account_data,
                      get_kin3_account_data_or_none)

logger = logging.getLogger('migration')
HTTP_STATUS_OK = 200
HTTP_STATUS_INTERNAL_ERROR = 500

INTERNAL_ADDRESS = f'{ APP_INTERNAL_SERVICE }/v1/internal'

@app.before_request
def set_start_time():
    # Add starting time
    flask.g.start_time = time.time()


@app.route('/accounts/<account_address>/status', methods=['GET'])
def account_status(account_address):
    logger.info(f'Received an account status request for address: {account_address}')
    return flask.jsonify({
        'is_burned': is_burned(account_address)
    }), HTTP_STATUS_OK


def migrate_zero_balance(account_address, kin3_account_data):
    """migrate an account with zero balance."""
    if kin3_account_data is None:
        try:
            main_account.create_account(account_address, starting_balance=0, fee=0)
            logger.info(f'Address: {account_address}, was not pre-created, created now')
        except KinErrors.AccountExistsError:
            pass
        statsd.increment('accounts_migrated', tags=['had_account:false', 'zero:true'])
    else:
        statsd.increment('accounts_migrated', tags=['had_account:true', 'zero:true'])
    return flask.jsonify({'code': HTTP_STATUS_OK, 'message': 'OK', 'balance': 0}), HTTP_STATUS_OK


def migrate_balance(account_address, proxy_address, channel, old_balance):
    """migrate account with non zero balance."""
    # Get tx builder, fee is 0 since we are whitelisted
    builder = main_account.get_transaction_builder(0)
    # Add the memo manually because use the builder directly
    builder.add_text_memo(build_memo(main_account.app_id, None))
    # Build tx
    build_migration_transaction(builder, proxy_address, account_address, old_balance)
    sign_tx(builder, channel, main_account.keypair.secret_seed)

    try:
        return main_account.submit_transaction(builder)
    except KinErrors.AccountExistsError:
        # The proxy was already created, so migration already happened
        raise MigrationErrors.AlreadyMigratedError(account_address)
    except KinErrors.AccountNotFoundError:
        return None


def migrate_balance_and_create_account(account_address, proxy_address, channel, old_balance):
    """migrate and create account with non zero balance."""
    # The user's account was not pre-created on the new blockchain
    logger.info(f'Address: {account_address}, was not pre-created, creating now')
    # Get tx builder, fee is 0 since we are whitelisted
    builder = main_account.get_transaction_builder(0)

    # Add the memo manually because use the builder directly
    builder.add_text_memo(build_memo(main_account.app_id, None))
    build_create_transaction(builder, proxy_address, account_address, old_balance)
    sign_tx(builder, channel, main_account.keypair.secret_seed)
    try:
        return main_account.submit_transaction(builder)
    except KinErrors.AccountExistsError:
        # Race condition, the client sent two migration requests at once, one of them finished first
        raise MigrationErrors.AlreadyMigratedError(account_address)


@app.route('/migrate', methods=['POST'])
def migrate():
    account_address = flask.request.args.get('address', '')
    logger.info(f'Received migration request for address: {account_address}')
    # Verify the client's burn
    if not is_burned(account_address):
        raise MigrationErrors.AccountNotBurnedError(account_address)
    logger.info(f'Verified that account {account_address} is burned')

    kin2_account_data = get_kin2_account_data(account_address)
    kin3_account_data = get_kin3_account_data_or_none(account_address)  # can run in parallel with above

    # Get the account's old balance
    old_balance = get_old_balance(kin2_account_data, KIN_ISSUER)
    logger.info(f'Account {account_address} had {old_balance} kin')

    if old_balance == 0:
        return migrate_zero_balance(account_address, kin3_account_data)

    # Generate the keypair for the proxy account
    proxy_address = get_proxy_address(account_address, PROXY_SALT)
    logger.info(f'Generated proxy account with address: {proxy_address}')

    # Grab an available channel:
    with main_account.channel_manager.get_channel() as channel:
        tx_hash = None
        if kin3_account_data:
            tx_hash = migrate_balance(account_address, proxy_address, channel, old_balance)

        if tx_hash:  # migration succeeded above
            statsd.increment('accounts_migrated', tags=['had_account:true', 'zero:false'])
        else:
            tx_hash = migrate_balance_and_create_account(account_address, proxy_address, channel, old_balance)
            statsd.increment('accounts_migrated', tags=['had_account:false', 'zero:false'])

    logger.info(f'Successfully migrated address: {account_address} with {old_balance} balance, tx: {tx_hash}')

    statsd.increment('kin_migrated', value=old_balance)

    # calls marketplace-internal for updating wallet with created_date_kin3
    marking_as_burnt_address = f'{ INTERNAL_ADDRESS }/wallets/{ account_address }/burnt'
    is_burnt_check_response = requests.put(marking_as_burnt_address)
    if is_burnt_check_response.status_code != 204:
        logger.error(f'marking wallet { account_address } as burnt failed with { is_burnt_check_response.status_code }')

    return flask.jsonify({'code': HTTP_STATUS_OK, 'message': 'OK', 'balance': old_balance }), HTTP_STATUS_OK


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
