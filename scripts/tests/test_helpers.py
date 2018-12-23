import pytest
import json


def test_verify_burn():
    from kin.blockchain.horizon_models import AccountData
    from src.helpers import verify_burn

    with open('tests/not_burned_data') as f:
        not_burned_data = f.read()

    with open('tests/burned_data') as f:
        burned_data = f.read()

    with pytest.raises(AssertionError):
        verify_burn(AccountData(json.loads(not_burned_data), strict=False))

    verify_burn(AccountData(json.loads(burned_data), strict=False))


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

    expected_hash = '8d02af84e13b00c59bea65032f0ee151226b8fb7e2ac26d6e2d905d9d8603fce'
    builder = Builder('TEST', '', 0, 'SCOMIY6IHXNIL6ZFTBBYDLU65VONYWI3Y6EN4IDWDP2IIYTCYZBCCE6C')
    build_migration_transaction(builder, proxy_address, client_address, 0)
    # Client had no balance so we didnt need to pay him
    assert len(builder.ops) == 1
    assert builder.hash_hex() == expected_hash

    expected_hash = 'e61259818578fdbbc848b059f0c9356d2f9915b2c3abdbd5a99ee4a28a1881cc'
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

    expected_hash = '3fabebf710dd246184c832949abc596da8598b9718bf49f36a5931677ed70a41'
    builder = Builder('TEST', '', 0, 'SCOMIY6IHXNIL6ZFTBBYDLU65VONYWI3Y6EN4IDWDP2IIYTCYZBCCE6C')
    build_create_transaction(builder, proxy_address, client_address, 0)
    assert builder.hash_hex() == expected_hash