import logging

import kin.errors as KinErrors
from kin.transactions import build_memo
from .config import PROXY_SALT
from .helpers import (get_proxy_address,
                      sign_tx,
                      build_migration_transaction,
                      build_create_transaction,
                      get_burned_balance,
                      has_kin3_account)
from . import errors as MigrationErrors
from .init import statsd, main_account, cache

logger = logging.getLogger('migration')


def migrate_zero_balance(account_address, has_kin3):
    """migrate an account with zero balance."""
    if not has_kin3:
        try:
            main_account.create_account(account_address, starting_balance=0, fee=0)
            cache.set_has_kin3_account(account_address)
            logger.info(f'Address: {account_address}, was not pre-created, created now')
        except KinErrors.AccountExistsError:
            pass
        statsd.increment('accounts_migrated', tags=['had_account:false', 'zero:true'])
    else:
        statsd.increment('accounts_migrated', tags=['had_account:true', 'zero:true'])
    return 0


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


def migrate(account_address):
    # Verify the client's burn
    old_balance = get_burned_balance(account_address)

    has_kin3 = has_kin3_account(account_address)

    # Get the account's old balance
    logger.info(f'Account {account_address} had {old_balance} kin')

    if old_balance == 0:
        return migrate_zero_balance(account_address, has_kin3)

    # Generate the keypair for the proxy account
    proxy_address = get_proxy_address(account_address, PROXY_SALT)
    logger.info(f'Generated proxy account with address: {proxy_address}')

    # Grab an available channel:
    with main_account.channel_manager.get_channel() as channel:
        tx_hash = None
        if has_kin3:
            tx_hash = migrate_balance(account_address, proxy_address, channel, old_balance)

        if tx_hash:  # migration succeeded above
            statsd.increment('accounts_migrated', tags=['had_account:true', 'zero:false'])
        else:
            tx_hash = migrate_balance_and_create_account(account_address, proxy_address, channel, old_balance)
            statsd.increment('accounts_migrated', tags=['had_account:false', 'zero:false'])

    logger.info(f'Successfully migrated address: {account_address} with {old_balance} balance, tx: {tx_hash}')

    statsd.increment('kin_migrated', value=old_balance)
    return old_balance
