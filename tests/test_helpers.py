import pytest
from unittest.mock import patch
import json


def test_is_burned():
    from kin.blockchain.horizon_models import AccountData
    from src.helpers import is_burned

    with open('tests/not_burned_data') as f:
        not_burned_data = f.read()

    with open('tests/burned_data') as f:
        burned_data = f.read()

    account = AccountData(json.loads(not_burned_data), strict=False)
    with patch('src.helpers.get_account_data', lambda x: account):
        assert not is_burned(account.account_id)

    account = AccountData(json.loads(burned_data), strict=False)
    with patch('src.helpers.get_account_data', lambda x: account):
        assert is_burned(account.account_id)


def test_get_old_balance():
    from kin.blockchain.horizon_models import AccountData
    from src.helpers import get_old_balance

    with open('tests/no_kin_data') as f:
        no_kin_data = f.read()

    with open('tests/with_kin_data') as f:
        with_kin_data = f.read()

    KIN_ISSUER = 'GBC3SG6NGTSZ2OMH3FFGB7UVRQWILW367U4GSOOF4TFSZONV42UJXUH7'

    assert get_old_balance(AccountData(json.loads(no_kin_data), strict=False), KIN_ISSUER) == 0
    assert get_old_balance(AccountData(json.loads(with_kin_data), strict=False), KIN_ISSUER) == 123


def test_get_proxy_address():
    from src.helpers import get_proxy_address

    client_address = 'GC46XF47MU4NUBBSQJ4KZWLZLN37UECP2TI2IQRYLRUBNGMADHKZBFGL'
    salt = 'SCOMIY6IHXNIL6ZFTBBYDLU65VONYWI3Y6EN4IDWDP2IIYTCYZBCCE6C'
    expected_proxy = 'GB3MH57M5JPLTPNIVW7BFKTMXSX3JJF4BRXK2R2XD7HBPZ5JMQLUDPSY'

    assert get_proxy_address(client_address, salt) == expected_proxy


def test_build_migration_transaction():
    from kin import Builder
    from src.helpers import build_migration_transaction
    client_address = 'GC46XF47MU4NUBBSQJ4KZWLZLN37UECP2TI2IQRYLRUBNGMADHKZBFGL'
    proxy_address = 'GB3MH57M5JPLTPNIVW7BFKTMXSX3JJF4BRXK2R2XD7HBPZ5JMQLUDPSY'

    expected_hash = 'bdd602b552377f84b80ef34dea732be8094ba5eaf3cc45e7f8f22b1a26a32ed1'
    builder = Builder('TEST', '', 0, 'SCOMIY6IHXNIL6ZFTBBYDLU65VONYWI3Y6EN4IDWDP2IIYTCYZBCCE6C')
    build_migration_transaction(builder, proxy_address, client_address, 0)
    # Client had no balance so we didnt need to pay him
    assert len(builder.ops) == 1
    assert builder.hash_hex() == expected_hash

    expected_hash = '90034a54d814b781a555d29bb539f38779f43a6143cc1372893490eb325b42fc'
    builder = Builder('TEST', '', 0, 'SCOMIY6IHXNIL6ZFTBBYDLU65VONYWI3Y6EN4IDWDP2IIYTCYZBCCE6C')
    build_migration_transaction(builder, proxy_address, client_address, 1)
    # Client had balance so we need to pay him
    assert len(builder.ops) == 2
    assert builder.hash_hex() == expected_hash


def test_build_create_transaction():
    from kin import Builder
    from src.helpers import build_create_transaction
    client_address = 'GC46XF47MU4NUBBSQJ4KZWLZLN37UECP2TI2IQRYLRUBNGMADHKZBFGL'
    proxy_address = 'GB3MH57M5JPLTPNIVW7BFKTMXSX3JJF4BRXK2R2XD7HBPZ5JMQLUDPSY'

    expected_hash = '8a38e61f07ef53a910e34e1d9a94402a534c2e1ba57f25f5a153accc63e9d570'
    builder = Builder('TEST', '', 0, 'SCOMIY6IHXNIL6ZFTBBYDLU65VONYWI3Y6EN4IDWDP2IIYTCYZBCCE6C')
    build_create_transaction(builder, proxy_address, client_address, 0)
    assert builder.hash_hex() == expected_hash
