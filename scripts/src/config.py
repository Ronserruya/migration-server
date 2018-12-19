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
    MAIN_SEED = 'SDBDJVXHPVQGDXYHEVOBBV4XZUDD7IQTXM5XHZRLXRJVY5YMH4YUCNZC'
    CHANNEL_SALT = 'local'
    CHANNEL_COUNT = 10
    OLD_HORIZON = 'http://localhost:8000'
    NEW_HORIZON = 'http://localhost:8002'
    NEW_PASSPHRASE = 'private testnet'
    APP_ID = ANON_APP_ID
    STATSD_HOST = 'localhost'
    STATSD_PORT = 8125
else:
    MAIN_SEED = os.environ['MAIN_SEED']
    CHANNEL_SALT = get_instance_id()
    CHANNEL_COUNT = os.environ['CHANNEL_COUNT']
    OLD_HORIZON = os.environ['OLD_HORIZON']
    NEW_HORIZON = os.environ['NEW_HORIZON']
    NEW_PASSPHRASE = os.environ['NEW_PASSPHRASE']
    APP_ID = os.environ['APP_ID']
    STATSD_HOST = os.environ['STATSD_HOST']
    STATSD_PORT = os.environ['STATSD_PORT']
