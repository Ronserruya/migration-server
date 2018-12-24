"""Routes and main logic for the migration service"""

import time
import logging

import flask
from werkzeug.exceptions import HTTPException
from kin.transactions import build_memo
import kin.errors as KinErrors
from kin.blockchain.utils import is_valid_address

from init import app, statsd, old_client, main_account
from config import KIN_ISSUER, DEBUG
import errors as MigrationErrors
from helpers import (get_proxy_address,
                     get_old_balance,
                     sign_tx,
                     build_migration_transaction,
                     build_create_transaction,
                     verify_burn)

logger = logging.getLogger('migration')


@app.before_request
def before_request():
    # Add starting time
    flask.g.start_time = time.time()


@app.route('/migrate', methods=['POST'])
def migrate():
    client_address = flask.request.args.get('address', '')
    logger.info(f'Received migration request for address: {client_address}')
    # Verify the client's address
    if not is_valid_address(client_address):
        raise MigrationErrors.AddressInvalidError(client_address)

    # Verify the client's burn
    try:
        account_data = old_client.get_account_data(client_address)
    except KinErrors.AccountNotFoundError:
        raise MigrationErrors.AccountNotFoundError(client_address)

    try:
        verify_burn(account_data)
    except AssertionError:
        raise MigrationErrors.AccountNotBurnedError(client_address)
    logger.info(f'Verified that account {client_address} is burned')

    # Get the account's old balance
    old_balance = get_old_balance(account_data, KIN_ISSUER)
    logger.info(f'Account {client_address} had {old_balance} kin')

    # Generate the keypair for the proxy account
    proxy_address = get_proxy_address(client_address, main_account.keypair.secret_seed)
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
            build_create_transaction(builder, proxy_address, client_address, old_balance)
            sign_tx(builder, channel, main_account.keypair.secret_seed)
            tx_hash = main_account.submit_transaction(builder)

        logger.info(f'Successfully migrated address: {client_address} with {old_balance} balance, tx: {tx_hash}')
        statsd.increment('accounts_migrated')
        if old_balance > 0:
            statsd.increment('kin_migrated', value=old_balance)

    return flask.jsonify({'code': 200, 'message': 'OK'}), 200


@app.route('/status', methods=['GET'])
def status():
    logger.info(f'Received status request')
    account_status = main_account.get_status()['account']
    account_status['old_kin_issuer'] = KIN_ISSUER
    statsd.gauge('wallet_balance', account_status['balance'])
    statsd.gauge('total_channels', account_status['channels']['total_channels'])
    statsd.gauge('free_channels', account_status['channels']['free_channels'])
    return flask.jsonify(account_status), 200


@app.after_request
def after_request(response):
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
    logger.error(f'Http exception: {exception.__repr__()}')
    return flask.jsonify({'code': exception.code, 'message': exception.__str__()})


@app.errorhandler(Exception)
def error_handle(exception: Exception):
    # Log the exception and return an internal server error
    logger.error(f'Unexpected exception: {str(exception)}')
    return flask.jsonify(MigrationErrors.InternalError().to_dict()), 500


if __name__ == '__main__':
    if DEBUG:
        app.run('0.0.0.0', port=8000)
