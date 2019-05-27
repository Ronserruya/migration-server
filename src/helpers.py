"""Contains helper methods for the migration server"""

import logging
from hashlib import sha256
from . import errors as MigrationErrors

from kin import Builder
from kin.blockchain.horizon_models import AccountData
from kin_base.keypair import Keypair as BaseKeypair
from kin.blockchain.utils import is_valid_address
import kin.errors as KinErrors
from .config import KIN_ISSUER
from .init import old_client, new_client, cache

KIN_ASSET_CODE = 'KIN'

logger = logging.getLogger('migration')


def get_kin2_account_data(account_address):
    # Verify the client's address
    if not is_valid_address(account_address):
        raise MigrationErrors.AddressInvalidError(account_address)

    logger.info(f'getting kin2 account {account_address} from horizon')
    try:
        account_data = old_client.get_account_data(account_address)
    except KinErrors.AccountNotFoundError:
        raise MigrationErrors.AccountNotFoundError(account_address)
    return account_data


def has_kin3_account(account_address):
    # Verify the client's address
    if not is_valid_address(account_address):
        raise MigrationErrors.AddressInvalidError(account_address)

    if cache.has_kin3_account(account_address):
        return True

    logger.info(f'getting kin3 account {account_address} from horizon')

    try:
        account = new_client.get_account_data(account_address)
        logger.info(f'found account {account_address} on kin3')
        cache.set_has_kin3_account(account_address)
        return True
    except KinErrors.AccountNotFoundError:
        return False


def is_burned(account_data: AccountData) -> bool:
    """Check that an account is burned"""
    # There are other ways to burn an account, but this is the way we do it
    # Only signer is the master signer, and its weight is 0
    burned_balance = cache.get_burned_balance(account_data.account_id)
    if burned_balance is not None:
        return True

    if len(account_data.signers) != 1 or account_data.signers[0].weight != 0:
        return False

    cache.set_burned_balance(account_data.account_id, get_old_balance(account_data))
    return True


def get_old_balance(account_data: AccountData) -> float:
    """Get the balance the user had on the old blockchain"""
    old_balance = 0
    for balance in account_data.balances:
        if balance.asset_code == KIN_ASSET_CODE and balance.asset_issuer == KIN_ISSUER:
            old_balance = balance.balance
            break

    return old_balance


def get_burned_balance(account_address):
    """return balance only if the account is burned"""
    burned_balance = cache.get_burned_balance(account_address)
    if burned_balance is not None:
        logger.info(f'got burned balance {burned_balance} from cache for {account_address}')
        return burned_balance

    # not cached - get from horizon
    kin2_account_data = get_kin2_account_data(account_address)
    if not is_burned(kin2_account_data):
        raise MigrationErrors.AccountNotBurnedError(account_address)

    old_balance = get_old_balance(kin2_account_data)

    logger.info(f'Verified that account {account_address} is burned with {burned_balance}')
    return old_balance


def build_migration_transaction(builder: Builder, client_address: str, old_balance: float):
    """Builder a transaction that will migrate an account"""
    # Next we pay the kin to the client
    builder.append_payment_op(destination=client_address,
                              amount=str(old_balance),
                              source=builder.address)


def build_create_transaction(builder: Builder, client_address: str, old_balance: float):
    """
    Build a transaction that will create the new account,
    in the rare case someone we didn't pre-create tries to migrate
    """
    # Next we create the client's account
    builder.append_create_account_op(destination=client_address,
                                     starting_balance=str(old_balance),
                                     source=builder.address)


def sign_tx(builder: Builder, channel: str, seed: str):
    """Set the channel and sign with both the channel and the main seed"""
    builder.set_channel(channel)
    builder.sign(channel)
    builder.sign(seed)
