# Migration-server
A server that is used to migrate a user from the old kin blockchain to the new one

# View test blockchain activity
https://kin3test.kinexplorer.com/

## Prerequisites
* Docker
* docker-compose
* (optional) datadog-agent to report metrics to

## Configuration
The server can be configured from the docker-compose.yml file


|          Variable          | Description                                                                                                                                                                                                                     |
|:--------------------------:|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| MAIN_SEED          | The seed of the account that will fund/create new accounts                                                                                                                                                                                      |
| PROXY_SALT          | A string that is used when checking if an account was already migrated|
| CHANNEL_COUNT            | Number of channels that will be used                                                                                                                                                                                                                                                                                                                                                                                       |
| KIN_ISSUER                 | Issuer of the kin asset on the old blockchain                                                                                                                                                                                                 |
| OLD_HORIZON                 | URL of horizon for the old blockchain|
| NEW_HORIZON         | URL of horizon for the new blockchain                                                                                                                                                                                       |
| NEW_PASSPHRASE                | The network passphrase for the new blockchain                                                                                                                         |
| APP_ID                | The app id (used to identify transactions)                                                                                                                                                                                                                 |
| STATSD_HOST             | Host of the datadog-agent                                                                                                                                                      |
| STATSD_PORT              | The datadog-agent statsd port                                                                                                                                                    |
| DEBUG              | Should be 'FALSE'|
If you wish to run the server in debug, you can just run the 'app.py' file (without the docker)


## Running the server
```bash
$ docker-compose up -d
```

Logs can be accessed with
```bash
$ docker-compose logs
```

**When running with 'DEBUG'='FALSE', the server is expecting to run on an amazon ec2 instance**

## External API (Test host: https://migration-devplatform-playground.developers.kinecosystem.com)


**GET '/status'**
```json
{
  "app_id": "mgsr",
  "balance": 9754,
  "channels": {
    "free_channels": 7,
    "non_free_channels": 3,
    "total_channels": 10
  },
  "old_kin_issuer": "GBC3SG6NGTSZ2OMH3FFGB7UVRQWILW367U4GSOOF4TFSZONV42UJXUH7",
  "public_address": "GDT7ZKBIKREQNZ3KRJA2QFF3KC3IAEAKAAIOHIISDMCIYMNW3UKOCW6R"
}
```

**POST '/migrate?address=<>'**
```json
{
  "code": 200,
  "message": "OK",
  "balance: <balance sent to migrated account>"
}
```

### Errors:

**HTTP 400**
Account not burned:
```json
{
  "code": 4001,
  "message": "Account GDMBQNC3JIAJKBCRFIFYNZVNYIBXBQ2CX2QP3KSDO72NZSAXT6PIGIVH was not burned"
}
```

Account already migrated:
```json
{
  "code": 4002,
  "message": "Account GC46XF47MU4NUBBSQJ4KZWLZLN37UECP2TI2IQRYLRUBNGMADHKZBFGL was already migrated"
}
```

Invalid public address:
```json
{
  "code": 4003,
  "message": "Address: blablabla is not a valid address"
}
```

**HTTP 404**
Account not found:
```json
{
  "code": 4041,
  "message": "Account GB4AG5DILURF4O3NFCH5BF4M7PZ2ZF5WOAL6M7CQZX2DSRQ5OJ4224UQ was not found"
}
```
