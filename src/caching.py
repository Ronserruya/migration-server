class Cache:
    def __init__(self, redis_conn):
        self.redis_conn = redis_conn

    def is_migrated(self, account_address):
        return self.redis_conn.get(f'migrated:{account_address}') is not None

    def set_migrated(self, account_address):
        return self.redis_conn.set(f'migrated:{account_address}', '1')

    def get_burned_balance(self, account_address):
        balance = self.redis_conn.get(f'burned_balance:{account_address}')
        if balance is None:
            return None

        return int(balance)

    def set_burned_balance(self, account_address, balance):
        return self.redis_conn.set(f'burned_balance:{account_address}', balance)

    def has_kin3_account(self, account_address):
        return self.redis_conn.get(f'has_kin3:{account_address}') is not None

    def set_has_kin3_account(self, account_address):
        return self.redis_conn.set(f'has_kin3:{account_address}', '1')
        # XXX these keys can be refilled with data from blockchain
