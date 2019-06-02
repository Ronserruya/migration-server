import logging

import kin.errors as KinErrors
from .helpers import (sign_tx,
                      build_migration_transaction,
                      build_create_transaction,
                      get_burned_balance,
                      has_kin3_account, get_proxy_address)
from . import errors as MigrationErrors
from .init import statsd, main_account, cache

logger = logging.getLogger('migration')


def migrate_zero_balance(account_address):
    """migrate an account with zero balance."""
    try:
        tx_hash = main_account.create_account(account_address,
                                              starting_balance=0,
                                              fee=0)
        cache.set_has_kin3_account(account_address)
        logger.info(f'Address: {account_address}, was not pre-created, created now with 0 balance')
        return tx_hash
    except KinErrors.AccountExistsError:
        cache.set_has_kin3_account(account_address)
        return '<already exists>'


def migrate_balance(account_address, old_balance):
    """migrate account with non zero balance."""
    logger.info(f'Address: {account_address}, was created, sending {old_balance} kin')
    try:
        return main_account.send_kin(account_address,
                                     amount=old_balance,
                                     fee=0)
    except KinErrors.AccountNotFoundError:
        return None


def migrate_balance_and_create_account(account_address, old_balance):
    """migrate and create account with non zero balance."""
    # The user's account was not pre-created on the new blockchain
    logger.info(f'Address: {account_address}, was not pre-created, creating now with {old_balance} balance')
    try:
        return main_account.create_account(account_address,
                                           starting_balance=old_balance,
                                           fee=0)
    except KinErrors.AccountExistsError:
        # Race condition, the client sent two migration requests at once, one of them finished first
        raise MigrationErrors.AlreadyMigratedError(account_address)


def migrate(account_address):
    """
    check if burned

    get balance

    if balance is 0, and account pre-created do nothing
    if balance is 0, and account not pre-created create account with 0

    if proxy account exists, skip funding

    if account pre-created "balance" send kin
    if account not pre-created create account with "balance"
    """
    # Verify the client's burn
    old_balance = get_burned_balance(account_address)  # throws when not burned
    has_kin3 = has_kin3_account(account_address)

    # Get the account's old balance
    logger.info(f'Account {account_address} had {old_balance} kin')

    if old_balance == 0:
        if has_kin3:
            tx_hash = '<already exists>'
            logger.info(f'Address: {account_address}, was created for 0 balance account')
        else:
            tx_hash = migrate_zero_balance(account_address)

        statsd.increment('accounts_migrated', tags=[f'had_account:{has_kin3}', 'zero:true'])
        logger.info(f'Successfully migrated address: {account_address} with {old_balance} balance, tx: {tx_hash}')
        return 0

    proxy_address = get_proxy_address(account_address)
    has_proxy = has_kin3_account(proxy_address)
    if has_proxy:  # skip funding
        statsd.increment('skip_funding', tags=[f'had_account:{has_kin3}'])  # should expect has_kin3 to always be true
        logger.warning(f'skipping funding {account_address} due to proxy account {proxy_address} existence')
        raise MigrationErrors.AlreadyMigratedError(account_address)

    tx_hash = None
    if has_kin3:
        tx_hash = migrate_balance(account_address, old_balance)

    if not tx_hash:  # migration can fail if the wallet doesnt exist on kin3 for some reason
        tx_hash = migrate_balance_and_create_account(account_address, old_balance)

    statsd.increment('accounts_migrated', tags=[f'had_account:{has_kin3}', 'zero:false'])
    logger.info(f'Successfully migrated address: {account_address} with {old_balance} balance, tx: {tx_hash}')

    statsd.increment('kin_migrated', value=old_balance)
    return old_balance
