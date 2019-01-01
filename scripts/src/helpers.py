"""Contains helper methods for the migration server"""

from hashlib import sha256

from kin import Builder
from kin.blockchain.horizon_models import AccountData
from kin_base.keypair import Keypair as BaseKeypair

KIN_ASSET_CODE = 'KIN'


def is_burned(account_data: AccountData) -> bool:
    """Check that an account is burned"""
    # There are other ways to burn an account, but this is the way we do it
    # Only signer is the master signer, and its weight is 0
    if len(account_data.signers) != 1 or account_data.signers[0].weight != 0:
        return False
    return True


def get_proxy_address(address: str, salt: str) -> str:
    """Generate a deterministic keypair using an address and a salt"""
    raw_seed = sha256((address + salt).encode()).digest()
    keypair = BaseKeypair.from_raw_seed(raw_seed)
    return keypair.address().decode()


def get_old_balance(account_data: AccountData, kin_issuer: str) -> float:
    """Get the balance the user had on the old blockchain"""
    old_balance = 0
    for balance in account_data.balances:
        if balance.asset_code == KIN_ASSET_CODE and balance.asset_issuer == kin_issuer:
            old_balance = balance.balance
            break

    return old_balance


def build_migration_transaction(builder: Builder, proxy_address: str,
                                client_address: str, old_balance: float):
    """Builder a transaction that will migrate an account"""

    # First we create the proxy account, this will fail if the migration already happened
    builder.append_create_account_op(destination=proxy_address,
                                     starting_balance=str(0),
                                     source=builder.address)

    if old_balance > 0:
        # Next we pay the kin to the client
        builder.append_payment_op(destination=client_address,
                                  amount=str(old_balance),
                                  source=builder.address)


def build_create_transaction(builder: Builder, proxy_address: str,
                             client_address: str, old_balance: float):
    """
    Build a transaction that will create the new account,
    in the rare case someone we didn't pre-create tries to migrate
    """

    # First we create the proxy account, this will fail if the migration already happened
    builder.append_create_account_op(destination=proxy_address,
                                     starting_balance=str(0),
                                     source=builder.address)

    # Next we create the client's account
    builder.append_create_account_op(destination=client_address,
                                     starting_balance=str(old_balance),
                                     source=builder.address)


def sign_tx(builder: Builder, channel: str, seed: str):
    """Set the channel and sign with both the channel and the main seed"""
    builder.set_channel(channel)
    builder.sign(channel)
    builder.sign(seed)
