"""Initialization for the migration service"""

import logging
import uuid

import kin
from kin.utils import create_channels
import flask
from flask_log_request_id import RequestID, RequestIDLogFilter
from flask_log_request_id.parser import amazon_elb_trace_id
from flask_cors import CORS
from datadog import DogStatsd

import config


def req_id_generator() -> str:
    """
    Generate a unique request id, used when the request id cannot be fetched from the elb headers
    """
    # 8 chars long should be long enough, add the 'Generated' prefix to know not to search for this id in the elb logs
    return f'Generated-{uuid.uuid4()[:8]}'


# Setup app
app = flask.Flask(__name__)
# Allow CORS
CORS(app)
# Inject request id to a request's context
RequestID(app, request_id_parser=amazon_elb_trace_id, request_id_generator=req_id_generator)

# Setup logging
logger = logging.getLogger(__name__)
logger.setLevel('INFO')
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s | level=%(levelname)s | request_id=%(request_id)s | %(message)s'))
handler.addFilter(RequestIDLogFilter())
logger.addHandler(handler)

# Setup DogStatsd
statsd = DogStatsd(host=config.STATSD_HOST, port=config.STATSD_PORT)

# Setup kin
# Passphrase is not needed for the old environment since we dont send any txs to it
old_env = kin.Environment('OLD', config.OLD_HORIZON, '')
new_env = kin.Environment('NEW', config.NEW_HORIZON, config.NEW_PASSPHRASE)

old_client = kin.KinClient(old_env)
new_client = kin.KinClient(new_env)

channels = create_channels(config.MAIN_SEED, new_env, config.CHANNEL_COUNT, 0, config.CHANNEL_SALT)
main_account = new_client.kin_account(config.MAIN_SEED, channels, app_id=config.APP_ID)

logger.info(f'Initialized app with address: {config.MAIN_SEED}, '
            f'Old horizon: {config.OLD_HORIZON}, '
            f'New horizon: {config.NEW_HORIZON}')



