# Copyright The IETF Trust 2021, All Rights Reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

__author__ = 'Slavomir Mazur'
__copyright__ = 'Copyright The IETF Trust 2021, All Rights Reserved'
__license__ = 'Apache License, Version 2.0'
__email__ = 'slavomir.mazur@pantheon.tech'

import json
import os
import sys
from collections import OrderedDict

import redis

from redisConnections.redisConnection import RedisConnection
from utility.create_config import create_config


# NOTE: ideally, this should run after we have verified that RedisConnections actually works,
#       i.e. after test_redisModulesConnection has run. I'm not sure if there's a sensible way to do this though.
def create_module_key(module: dict):
    return f'{module.get("name")}@{module.get("revision")}/{module.get("organization")}'


def load_catalog_data():
    config = create_config()
    redis_host = config.get('DB-Section', 'redis-host')
    redis_port = config.get('DB-Section', 'redis-port')
    redis_cache = redis.Redis(host=redis_host, port=redis_port)  # pyright: ignore
    redis_connection = RedisConnection()
    resources_path = os.path.join(os.environ['BACKEND'], 'tests/resources')
    try:
        print(f'Loading cache file from path {resources_path}')
        with open(os.path.join(resources_path, 'cache_data.json'), 'r') as file_load:
            catalog_data = json.load(file_load, object_pairs_hook=OrderedDict)
            print('Content of cache file loaded successfully.')
    except (FileNotFoundError, json.JSONDecodeError):
        print('Failed to load data from .json file')
        sys.exit(1)

    catalog = catalog_data.get('yang-catalog:catalog')
    modules = catalog['modules']['module']
    vendors = catalog['vendors']['vendor']

    for module in modules:
        if module['name'] == 'yang-catalog' and module['revision'] == '2018-04-03':
            redis_cache.set('yang-catalog@2018-04-03/ietf', json.dumps(module))
            redis_connection.populate_modules([module])
            print('yang-catalog@2018-04-03 module set in Redis')
            break

    catalog_data_json = json.JSONDecoder(object_pairs_hook=OrderedDict).decode(json.dumps(catalog_data))[
        'yang-catalog:catalog'
    ]
    modules = catalog_data_json['modules']
    vendors = catalog_data_json.get('vendors', {})

    # Fill Redis db=1 with modules data
    modules_data = {create_module_key(module): module for module in modules.get('module', [])}
    redis_connection.set_module(modules_data, 'modules-data')
    print(f'{len(modules.get("module", []))} modules set in Redis.')
    redis_connection.populate_implementation(vendors.get('vendor', []))
    redis_connection.reload_vendors_cache()
    print(f'{len(vendors.get("vendor", []))} vendors set in Redis.')


def main():
    load_catalog_data()


if __name__ == '__main__':
    main()
