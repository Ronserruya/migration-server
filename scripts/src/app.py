"""Routes and main logic for the migration service"""

import time
from hashlib import sha256

import flask
import kin
from kin.blockchain.horizon_models import AccountData
from kin_base.keypair import Keypair as BaseKeypair
from kin.transactions import build_memo
import kin.errors as KinErrors
from kin.blockchain.utils import is_valid_address

from __init__ import app, statsd, logger, old_client, main_account
from config import KIN_ISSUER
import errors as MigrationErrors


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
    proxy_keypair = get_proxy_keypair(client_address, main_account.keypair.secret_seed)
    logger.info(f'Generated proxy account with address: {proxy_keypair.public_address}')

    # Build tx
    builder = build_migration_transaction(main_account, proxy_keypair, client_address, old_balance)
    # Grab an available channel:
    with main_account.channel_manager.get_channel() as channel:
        builder.set_channel(channel)
        # Sign with the main account, channel, and proxy
        builder.sign(channel)
        builder.sign(proxy_keypair.secret_seed)
        builder.sign(main_account.keypair.secret_seed)

        try:
            tx_hash = main_account.submit_transaction(builder)
        except KinErrors.AccountExistsError:
            # The proxy was already created, so migration already happened
            raise MigrationErrors.AlreadyMigratedError(client_address)
        except KinErrors.AccountNotFoundError:
            # The user's account was not pre-created on the new blockchain
            logger.info(f'Address: {client_address}, was not pre-created, creating now')
            builder = build_create_transaction(main_account, proxy_keypair, client_address, old_balance)
            builder.set_channel(channel)
            # Sign with the main account, channel, and proxy
            builder.sign(channel)
            builder.sign(proxy_keypair.secret_seed)
            builder.sign(main_account.keypair.secret_seed)
            tx_hash = main_account.submit_transaction(builder)

        logger.info(f'Successfully migrated address: {client_address} with {old_balance} balance, tx: {tx_hash}')
        statsd.increment('accounts_migrated')
        if old_balance > 0:
            statsd.increment('kin_migrated', value=old_balance)

    return flask.jsonify({'code': 200, 'message': 'OK'}), 200


def verify_burn(account_data: AccountData):
    """Check that an account is burned"""
    # Only signer is the master signer, and its weight is 0
    assert len(account_data.signers == 1)
    assert account_data.signers[0].weight == 0


def get_proxy_keypair(address: str, salt: str) -> kin.Keypair:
    """Generate a deterministic keypair using an address and a salt"""
    raw_seed = sha256((address + salt).encode()).digest()
    seed = BaseKeypair.from_raw_seed(raw_seed).seed().decode()
    return kin.Keypair(seed)


def get_old_balance(account_data: AccountData, kin_issuer: str) -> float:
    """Get the balance the user had on the old blockchain"""
    old_balance = 0
    for balance in account_data.balances:
        if balance.asset_code == 'KIN' and balance.asset_issuer == kin_issuer:
            old_balance = balance.balance
            break

    return old_balance


def build_migration_transaction(account: kin.KinAccount, proxy_keypair: kin.Keypair, client_address: str,
                                old_balance: float) -> kin.Builder:
    """Builder a transaction that will migrate an account"""
    # Fee is 0 since we are whitelisted
    builder = account.get_transaction_builder(fee=0)
    # Add the memo manually because use the builder directly
    builder.add_text_memo(build_memo(account.app_id, None))

    # First we create the proxy account, this will fail if the migration already happened
    builder.append_create_account_op(proxy_keypair.public_address,
                                     starting_balance=old_balance,
                                     source=account.keypair.public_address)

    if old_balance > 0:
        # Next we move the kin from the proxy account to the new created account
        builder.append_payment_op(client_address, old_balance, source=proxy_keypair.public_address)

    # Lastly, we burn the proxy account, just for extra security
    builder.append_set_options_op(master_weight=0, source=proxy_keypair.public_address)

    return builder


def build_create_transaction(account: kin.KinAccount, proxy_keypair: kin.Keypair, client_address: str,
                             old_balance: float) -> kin.Builder:
    """
    Build a transaction that will create the new account,
    in the rare case someone we didn't pre-create tries to migrate
    """
    # Fee is 0 since we are whitelisted
    builder = account.get_transaction_builder(fee=0)
    # Add the memo manually because use the builder directly
    builder.add_text_memo(build_memo(account.app_id, None))

    # First we create the proxy account, this will fail if the migration already happened
    builder.append_create_account_op(proxy_keypair.public_address,
                                     starting_balance=old_balance,
                                     source=account.keypair.public_address)

    # Next we create the client's account with the proxy
    builder.append_create_account_op(client_address,
                                     starting_balance=old_balance,
                                     source=proxy_keypair.public_address)

    # Lastly, we burn the proxy account, just for extra security
    builder.append_set_options_op(master_weight=0, source=proxy_keypair.public_address)

    return builder


@app.route('/status', methods=['GET'])
def status():
    account_status = main_account.get_status()['account']
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


@app.errorhandler(Exception)
def error_handle(exception: Exception):
    if issubclass(exception.__class__, MigrationErrors.MigrationError):
        # If its one of our custom errors, report it to statsd
        statsd.increment(exception.statsd_metric)
        logger.error(exception.error)
        return flask.jsonify(exception.to_dict()), exception.http_code
    # Log the exception and return an internal server error
    logger.error(f'Unexpected exception: {str(exception)}')
    return flask.jsonify(MigrationErrors.InternalError().to_dict()), 500