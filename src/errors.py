"""Contains errors specific to the migration server"""


class InternalError(Exception):
    """Internal error to use when when an unexpected exception happens"""
    error = 'Internal server error'
    code = 500

    def to_dict(self):
        return {'code': self.code, 'message': self.error}


class MigrationError(Exception):
    """Base class for errors"""
    def __init__(self, message):
        self.error = message

    def to_dict(self):
        return {'code': self.code, 'message': self.error}


class AccountNotBurnedError(MigrationError):
    def __init__(self, address):
        self.code = 4001
        self.http_code = 400
        self.statsd_metric = 'client_not_burned'
        message = f'Account {address} was not burned'
        super(AccountNotBurnedError, self).__init__(message)


class AccountNotFoundError(MigrationError):
    def __init__(self, address):
        self.code = 4041
        self.http_code = 404
        self.statsd_metric = 'client_not_found'
        message = f'Account {address} was not found'
        super(AccountNotFoundError, self).__init__(message)


class AlreadyMigratedError(MigrationError):
    def __init__(self, address):
        self.code = 4002
        self.http_code = 400
        self.statsd_metric = 'client_already_migrated'
        message = f'Account {address} was already migrated'
        super(AlreadyMigratedError, self).__init__(message)


class AddressInvalidError(MigrationError):
    def __init__(self, address):
        self.code = 4003
        self.http_code = 400
        self.statsd_metric = 'client_address_invalid'
        message = f'Address: {address} is not a valid address'
        super(AddressInvalidError, self).__init__(message)