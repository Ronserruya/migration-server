import logging
import requests
from .config import INTERNAL_SERVICE


logger = logging.getLogger('migration')
session = requests.Session()


def mark_as_burnt(account_address):
    """calls marketplace-internal for updating wallet with created_date_kin3"""
    url = f'{INTERNAL_SERVICE}/v1/internal/wallets/{account_address}/burnt'
    try:
        res = session.put(url)
        res.raise_for_status()

    except requests.RequestException as e:
        logger.error(f'marking wallet {account_address} as burnt failed with {e}')