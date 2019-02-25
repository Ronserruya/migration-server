"""Routes and main logic for the migration service"""

import time
import logging

import flask
from werkzeug.exceptions import HTTPException

import kin.errors as KinErrors
from kin.transactions import build_memo
from kin.blockchain.utils import is_valid_address

import errors as MigrationErrors
from init import app, statsd, old_client, main_account
from config import KIN_ISSUER, DEBUG, PROXY_SALT
from helpers import (get_proxy_address,
                     get_old_balance,
                     sign_tx,
                     build_migration_transaction,
                     build_create_transaction,
                     is_burned)

logger = logging.getLogger('migration')
HTTP_STATUS_OK = 200
HTTP_STATUS_INTERNAL_ERROR = 500


@app.before_request
def set_start_time():
    # Add starting time
    flask.g.start_time = time.time()


@app.route('/migrate', methods=['POST'])
def migrate():
    client_address = flask.request.args.get('address', '')
    logger.info(f'Received migration request for address: {client_address}')
    # Verify the client's address
    if not is_valid_address(client_address):
        raise MigrationErrors.AddressInvalidError(client_address)

    try:
        account_data = old_client.get_account_data(client_address)
    except KinErrors.AccountNotFoundError:
        raise MigrationErrors.AccountNotFoundError(client_address)

    # Verify the client's burn
    if not is_burned(account_data):
        raise MigrationErrors.AccountNotBurnedError(client_address)
    logger.info(f'Verified that account {client_address} is burned')

    # Get the account's old balance
    old_balance = get_old_balance(account_data, KIN_ISSUER)
    logger.info(f'Account {client_address} had {old_balance} kin')

    # Generate the keypair for the proxy account
    proxy_address = get_proxy_address(client_address, PROXY_SALT)
    logger.info(f'Generated proxy account with address: {proxy_address}')

    # Get tx builder, fee is 0 since we are whitelisted
    builder = main_account.get_transaction_builder(0)

    # Add the memo manually because use the builder directly
    builder.add_text_memo(build_memo(main_account.app_id, None))

    # Build tx
    build_migration_transaction(builder, proxy_address, client_address, old_balance)
    # Grab an available channel:
    with main_account.channel_manager.get_channel() as channel:
        sign_tx(builder, channel, main_account.keypair.secret_seed)

        try:
            tx_hash = main_account.submit_transaction(builder)
        except KinErrors.AccountExistsError:
            # The proxy was already created, so migration already happened
            raise MigrationErrors.AlreadyMigratedError(client_address)
        except KinErrors.AccountNotFoundError:
            # We expect most account to be created, so its better to "ask for forgiveness, not for permission"
            # The user's account was not pre-created on the new blockchain
            logger.info(f'Address: {client_address}, was not pre-created, creating now')
            # Get tx builder, fee is 0 since we are whitelisted
            builder = main_account.get_transaction_builder(0)

            # Add the memo manually because use the builder directly
            builder.add_text_memo(build_memo(main_account.app_id, None))
            build_create_transaction(builder, proxy_address, client_address, old_balance)
            sign_tx(builder, channel, main_account.keypair.secret_seed)
            try:
                tx_hash = main_account.submit_transaction(builder)
            except KinErrors.AccountExistsError:
                # Race condition, the client sent two migration requests at once, one of them finished first
                raise MigrationErrors.AlreadyMigratedError(client_address)

    # If the user had 0 kin, we didn't try to pay him, and might missed that he is not created
    if old_balance == 0:
        try:
            main_account.create_account(client_address, starting_balance=old_balance, fee=0)
            logger.info(f'Address: {client_address}, was not pre-created, created now')
        except KinErrors.AccountExistsError:
            pass

    logger.info(f'Successfully migrated address: {client_address} with {old_balance} balance, tx: {tx_hash}')
    statsd.increment('accounts_migrated')
    if old_balance > 0:
        statsd.increment('kin_migrated', value=old_balance)

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
    statsd.histogram('response_time', response_time, tags=[f'path:{flask.request.path}'])
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
    logger.error(f'Http exception: {repr(exception)}')
    return flask.jsonify({'code': exception.code, 'message': exception.__str__()}), exception.code


@app.errorhandler(Exception)
def error_handle(exception: Exception):
    # Log the exception and return an internal server error
    logger.error(f'Unexpected exception: {str(exception)}')
    return flask.jsonify(MigrationErrors.InternalError().to_dict()), HTTP_STATUS_INTERNAL_ERROR


if __name__ == '__main__':
    if DEBUG:
        app.run('0.0.0.0', port=8000)
