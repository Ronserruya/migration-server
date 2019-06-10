import os
import pytest
from unittest.mock import patch
import json
from kin.blockchain.horizon_models import AccountData
from kin_base.operation import CreateAccount, Payment
from kin import Keypair

os.environ['UNITTEST'] = 'True'

def gen_address():
    return Keypair(Keypair.generate_seed()).public_address


def test_has_kin3_account():
    import kin.errors as KinErrors
    from src.helpers import has_kin3_account
    from src.init import cache

    account = gen_address()
    with patch('src.helpers.new_client.get_account_data', lambda x: 'blah'):
        assert has_kin3_account(account)
    assert cache.has_kin3_account(account)

    account = gen_address()
    def raise_error(x):
        raise KinErrors.AccountNotFoundError
    with patch('src.helpers.new_client.get_account_data', raise_error):
        assert not has_kin3_account(account)
    assert not cache.has_kin3_account(account)


def test_migrate_zero_with_account():
    from src.migration import migrate

    account = gen_address()
    with patch('src.migration.get_burned_balance', lambda x: 0):
        with patch('src.migration.has_kin3_account', lambda x: True):
            with patch('src.migration.main_account.create_account') as create_account:
                assert 0 == migrate(account)
                create_account.assert_not_called()


def test_migrate_zero_without_account():
    # 3 migrate non zero with account
    # 4 migrate non zero without account
    from src.migration import migrate

    account = gen_address()
    with patch('src.migration.get_burned_balance', lambda x: 0):
        with patch('src.migration.has_kin3_account', lambda x: False):
            with patch('src.migration.main_account.create_account') as create_account:
                assert 0 == migrate(account)
                create_account.assert_called_with(account, fee=0, starting_balance=0)


def test_migrate_non_zero_with_account():
    from src.migration import migrate

    account = gen_address()
    with patch('src.migration.get_burned_balance', lambda x: 7):
        with patch('src.migration.has_kin3_account', lambda x: x == account):
            with patch('src.migration.main_account.submit_transaction') as submit_transaction:
                assert 7 == migrate(account)
                builder = submit_transaction.call_args[0][0]
                assert isinstance(builder.ops[0], Payment)


def test_migrate_non_zero_without_account():
    from src.migration import migrate

    account = gen_address()
    with patch('src.migration.get_burned_balance', lambda x: 7):
        with patch('src.migration.has_kin3_account', lambda x: False):
            with patch('src.migration.main_account.submit_transaction') as submit_transaction:
                assert 7 == migrate(account)
                builder = submit_transaction.call_args[0][0]
                assert isinstance(builder.ops[0], CreateAccount)


def test_caching():
    from src.init import cache
    account = 'blah'
    assert not cache.is_migrated(account)
    cache.set_migrated(account)
    assert cache.is_migrated(account)

    assert cache.get_burned_balance(account) is None
    cache.set_burned_balance(account, 7)
    assert cache.get_burned_balance(account) == 7
    cache.set_burned_balance(account, 0)
    assert cache.get_burned_balance(account) == 0

    assert not cache.has_kin3_account(account)
    cache.set_has_kin3_account(account)
    assert cache.has_kin3_account(account)


def test_is_burned():
    from src.helpers import is_burned

    with open('tests/not_burned_data') as f:
        not_burned_data = f.read()

    with open('tests/burned_data') as f:
        burned_data = f.read()

    with open('tests/zero_kin') as f:
        zero_kin = f.read()

    with open('tests/no_kin_data') as f:
        no_kin_data = f.read()

    account = AccountData(json.loads(not_burned_data), strict=False)
    with patch('src.helpers.get_kin2_account_data', lambda x: account):
        assert not is_burned(account)

    account = AccountData(json.loads(burned_data), strict=False)
    with patch('src.helpers.get_kin2_account_data', lambda x: account):
        assert is_burned(account)

    account = AccountData(json.loads(zero_kin), strict=False)
    with patch('src.helpers.get_kin2_account_data', lambda x: account):
        assert is_burned(account)

    account = AccountData(json.loads(no_kin_data), strict=False)
    with patch('src.helpers.get_kin2_account_data', lambda x: account):
        assert is_burned(account)


def test_get_old_balance():
    from src.helpers import get_old_balance
    from src import config

    with open('tests/no_kin_data') as f:
        no_kin_data = f.read()

    with open('tests/with_kin_data') as f:
        with_kin_data = f.read()

    config.KIN_ISSUER = 'GBC3SG6NGTSZ2OMH3FFGB7UVRQWILW367U4GSOOF4TFSZONV42UJXUH7'

    assert get_old_balance(AccountData(json.loads(no_kin_data), strict=False)) == 0
    assert get_old_balance(AccountData(json.loads(with_kin_data), strict=False)) == 123


def test_build_migration_transaction():
    from kin import Builder
    from src.helpers import build_migration_transaction
    client_address = 'GC46XF47MU4NUBBSQJ4KZWLZLN37UECP2TI2IQRYLRUBNGMADHKZBFGL'

    expected_hash = '1ccc7b3dc25499894a52d814227697785f0308a3a6b3145b987b01ce633a9bbd'
    builder = Builder('TEST', '', 0, 'SCOMIY6IHXNIL6ZFTBBYDLU65VONYWI3Y6EN4IDWDP2IIYTCYZBCCE6C')
    build_migration_transaction(builder, client_address, 0)
    # Client had no balance so we didnt need to pay him
    assert len(builder.ops) == 1
    assert builder.hash_hex() == expected_hash

    expected_hash = '6f7b15167783932c58c67b08f3011102b3ad00c84f61633092f2d4a862a3700b'
    builder = Builder('TEST', '', 0, 'SCOMIY6IHXNIL6ZFTBBYDLU65VONYWI3Y6EN4IDWDP2IIYTCYZBCCE6C')
    build_migration_transaction(builder, client_address, 1)
    # Client had balance so we need to pay him
    assert len(builder.ops) == 1
    assert builder.hash_hex() == expected_hash


def test_build_create_transaction():
    from kin import Builder
    from src.helpers import build_create_transaction
    client_address = 'GC46XF47MU4NUBBSQJ4KZWLZLN37UECP2TI2IQRYLRUBNGMADHKZBFGL'

    expected_hash = '52d6d97c4a1a3164d4a4c48ee8f49d87a0072a76ce19d84b360c56d106661e60'
    builder = Builder('TEST', '', 0, 'SCOMIY6IHXNIL6ZFTBBYDLU65VONYWI3Y6EN4IDWDP2IIYTCYZBCCE6C')
    build_create_transaction(builder, client_address, 0)
    assert builder.hash_hex() == expected_hash
