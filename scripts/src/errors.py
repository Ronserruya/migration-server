"""Contains errors specific to the migration server"""


class MigrationError(Exception):
    """Base class for errors"""
    def __init__(self, message):
        self.error = message

    def to_dict(self):
        return {'code': self.code, 'error': self.error}


class AccountNotBurnedError(MigrationError):
    def __init__(self, address):
        self.code = 4001
        self.http_code = 400
        self.statsd_param = 'client_not_burned'
        message = f'Account {address} was not burned'
        super(AccountNotBurnedError, self).__init__(message)


class AccountNotFoundError(MigrationError):
    def __init__(self, address):
        self.code = 4041
        self.http_code = 404
        self.statsd_param = 'client_not_found'
        message = f'Account {address} was not found'
        super(AccountNotFoundError, self).__init__(message)


class AlreadyMigratedError(MigrationError):
    def __init__(self, address):
        self.code = 4002
        self.http_code = 400
        self.statsd_param = 'client_already_migrated'
        message = f'Account {address} was already migrated'
        super(AlreadyMigratedError, self).__init__(message)

