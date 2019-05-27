import os

import requests
from kin.config import ANON_APP_ID


def get_instance_id() -> str:
    """Get the ec2 instance id to be used as a unique salt for the channels on this instance"""
    # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-metadata.html
    r = requests.get('http://169.254.169.254/latest/meta-data/instance-id')
    r.raise_for_status()
    return r.text


DEBUG = os.environ.get('DEBUG', 'TRUE')

# Can get bool from env variable, need to check the string
if DEBUG == 'TRUE':
    MAIN_SEED = 'SDO3BNCOUDHYLUT5FQ537PZZUPBTMSTRCQOCDJE3XF22LP7DPIUP2SDF'
    PROXY_SALT = 'pizza'
    CHANNEL_SALT = 'local'
    CHANNEL_COUNT = 10
    KIN_ISSUER = 'GBC3SG6NGTSZ2OMH3FFGB7UVRQWILW367U4GSOOF4TFSZONV42UJXUH7'
    OLD_HORIZON = 'https://horizon-playground.kininfrastructure.com'
    NEW_HORIZON = 'https://horizon-testnet.kininfrastructure.com'
    NEW_PASSPHRASE = 'Kin Testnet ; December 2018'
    APP_ID = ANON_APP_ID
    STATSD_HOST = 'localhost'
    STATSD_PORT = 8125
    REDIS_CONN = os.environ['REDIS_CONN'] # in the form of redis://localhost:6379/0
else:
    MAIN_SEED = os.environ['MAIN_SEED']
    PROXY_SALT = os.environ['PROXY_SALT']
    CHANNEL_SALT = get_instance_id()
    CHANNEL_COUNT = int(os.environ['CHANNEL_COUNT'])
    KIN_ISSUER = os.environ['KIN_ISSUER']
    OLD_HORIZON = os.environ['OLD_HORIZON']
    NEW_HORIZON = os.environ['NEW_HORIZON']
    NEW_PASSPHRASE = os.environ['NEW_PASSPHRASE']
    APP_ID = os.environ['APP_ID']
    STATSD_HOST = os.environ['STATSD_HOST']
    STATSD_PORT = int(os.environ['STATSD_PORT'])
    REDIS_CONN = os.environ['REDIS_CONN']
