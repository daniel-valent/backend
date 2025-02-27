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

# We always check result.is_json, so result.json will never return None.
# pyright: reportOptionalSubscript=false

__author__ = 'Richard Zilincik'
__copyright__ = 'Copyright The IETF Trust 2021, All Rights Reserved'
__license__ = 'Apache License, Version 2.0'
__email__ = 'richard.zilincik@pantheon.tech'

import json
import os
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from redis import RedisError
from werkzeug.exceptions import HTTPException

import api.views.admin as admin
from api.yangcatalog_api import app
from redisConnections.redis_users_connection import RedisUsersConnection

app_config = app.config


class TestApiAdminClass(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.resources_path = os.path.join(os.environ['BACKEND'], 'tests/resources')
        cls.client = app.test_client()
        cls.users = RedisUsersConnection()
        with open(os.path.join(cls.resources_path, 'payloads.json'), 'r') as f:
            content = json.load(f)
        fields = content['user']['input']
        cls.user_info_fields = {key.replace('-', '_'): value for key, value in fields.items()}
        with open(os.path.join(cls.resources_path, 'testlog.log'), 'r') as f:
            cls.test_log_text = f.read()
        with open(os.path.join(cls.resources_path, 'payloads.json'), 'r') as f:
            cls.payloads_content = json.load(f)

    def setUp(self):
        self.uid = self.users.create(temp=True, **self.user_info_fields)

    def tearDown(self):
        self.users.delete(self.uid, temp=True)

    def assertJsonResponse(self, response, status_code: int, field: str, value, contains: bool = False):  # noqa: N802
        self.assertEqual(response.status_code, status_code)
        self.assertTrue(response.is_json)
        data = response.json
        self.assertIn(field, data)
        if contains:
            self.assertIn(value, data[field])
        else:
            self.assertEqual(data[field], value)

    def test_catch_db_error(self):
        with app.app_context():

            def error():
                raise RedisError

            result = admin.catch_db_error(error)()

        self.assertEqual(result, ({'error': 'Server problem connecting to database'}, 500))

    def test_get_input(self):
        result = admin.get_input({'input': 'test'})
        self.assertEqual(result, 'test')

    def test_get_input_empty(self):
        try:
            admin.get_input(None)
        except HTTPException as e:
            self.assertEqual(e.description, 'bad-request - body can not be empty')

    def test_get_input_empty_no_input(self):
        try:
            admin.get_input({})
        except HTTPException as e:
            self.assertEqual(e.description, 'bad-request - body has to start with "input" and can not be empty')

    def test_logout(self):
        result = self.client.post('api/admin/logout')

        self.assertJsonResponse(result, 200, 'info', 'Success')

    def test_check(self):
        result = self.client.get('api/admin/check')

        self.assertJsonResponse(result, 200, 'info', 'Success')

    @mock.patch('builtins.open', mock.mock_open(read_data='test'))
    def test_read_admin_file(self):
        path = 'all_modules/yang-catalog@2018-04-03.yang'
        result = self.client.get(f'api/admin/directory-structure/read/{path}')

        self.assertJsonResponse(result, 200, 'info', 'Success')
        self.assertJsonResponse(result, 200, 'data', 'test')

    def test_read_admin_file_not_found(self):
        path = 'nonexistent'
        result = self.client.get(f'api/admin/directory-structure/read/{path}')

        self.assertJsonResponse(result, 400, 'description', 'error - file does not exist')

    def test_read_admin_file_directory(self):
        path = 'all_modules'
        result = self.client.get(f'api/admin/directory-structure/read/{path}')

        self.assertJsonResponse(result, 400, 'description', 'error - file does not exist')

    @mock.patch('os.unlink')
    def test_delete_admin_file(self, mock_unlink: mock.MagicMock):
        path = 'all_modules/yang-catalog@2018-04-03.yang'
        result = self.client.delete(f'api/admin/directory-structure/{path}')

        self.assertJsonResponse(result, 200, 'info', 'Success')
        self.assertJsonResponse(result, 200, 'data', f'directory of file {app_config.d_var}/{path} removed succesfully')

    @mock.patch('shutil.rmtree')
    def test_delete_admin_file_directory(self, mock_rmtree: mock.MagicMock):
        result = self.client.delete('api/admin/directory-structure')

        self.assertJsonResponse(result, 200, 'info', 'Success')
        self.assertJsonResponse(result, 200, 'data', f'directory of file {app_config.d_var}/ removed succesfully')

    def test_delete_admin_file_nonexistent(self):
        result = self.client.delete('api/admin/directory-structure/nonexistent')

        self.assertJsonResponse(result, 400, 'description', 'error - file or folder does not exist')

    @mock.patch('builtins.open', mock.mock_open())
    def test_write_to_directory_structure(self):
        path = 'all_modules/yang-catalog@2018-04-03.yang'
        result = self.client.put(f'api/admin/directory-structure/{path}', json={'input': {'data': 'test'}})

        self.assertJsonResponse(result, 200, 'info', 'Success')
        self.assertJsonResponse(result, 200, 'data', 'test')

    def test_write_to_directory_structure_not_found(self):
        path = 'nonexistent'
        result = self.client.put(f'api/admin/directory-structure/{path}', json={'input': {'data': 'test'}})

        self.assertJsonResponse(result, 400, 'description', 'error - file does not exist')

    @mock.patch('os.walk')
    @mock.patch('os.lstat')
    @mock.patch.object(Path, 'glob')
    @mock.patch.object(Path, 'stat')
    def test_get_var_yang_directory_structure(
        self,
        mock_stat: mock.MagicMock,
        mock_glob: mock.MagicMock,
        mock_lstat: mock.MagicMock,
        mock_walk: mock.MagicMock,
    ):
        good_stat = mock.MagicMock()
        good_stat.st_size = 0
        good_stat.st_gid = 0
        good_stat.st_uid = 0
        good_stat.st_mtime = 0
        bad_stat = mock.MagicMock()
        bad_stat.st_size = 0
        bad_stat.st_gid = 2354896
        bad_stat.st_uid = 2354896
        bad_stat.st_mtime = 0
        mock_stat.side_effect = [good_stat, bad_stat, good_stat, bad_stat]
        mock_glob.return_value = ()
        lstat = mock.MagicMock()
        lstat.st_mode = 0o777
        mock_lstat.return_value = lstat
        mock_walk.return_value = [('root', ('testdir', 'testdir2'), ('test', 'test2'))].__iter__()
        result = self.client.get('api/admin/directory-structure')

        structure = {
            'name': 'root',
            'files': [
                {'name': 'test', 'size': 0, 'group': 'root', 'user': 'root', 'permissions': '0o777', 'modification': 0},
                {
                    'name': 'test2',
                    'size': 0,
                    'group': 2354896,
                    'user': 2354896,
                    'permissions': '0o777',
                    'modification': 0,
                },
            ],
            'folders': [
                {
                    'name': 'testdir',
                    'size': 0,
                    'group': 'root',
                    'user': 'root',
                    'permissions': '0o777',
                    'modification': 0,
                },
                {
                    'name': 'testdir2',
                    'size': 0,
                    'group': 2354896,
                    'user': 2354896,
                    'permissions': '0o777',
                    'modification': 0,
                },
            ],
        }

        self.assertJsonResponse(result, 200, 'info', 'Success')
        self.assertJsonResponse(result, 200, 'data', structure)

    @mock.patch('os.listdir')
    def test_read_yangcatalog_nginx_files(self, mock_listdir: mock.MagicMock):
        mock_listdir.return_value = ['test']
        result = self.client.get('api/admin/yangcatalog-nginx')

        self.assertJsonResponse(result, 200, 'info', 'Success')
        self.assertJsonResponse(result, 200, 'data', ['sites-enabled/test', 'nginx.conf', 'conf.d/test'])

    @mock.patch('builtins.open', mock.mock_open(read_data='test'))
    def test_read_yangcatalog_nginx(self):
        result = self.client.get('api/admin/yangcatalog-nginx/test')

        self.assertJsonResponse(result, 200, 'info', 'Success')
        self.assertJsonResponse(result, 200, 'data', 'test')

    @mock.patch('builtins.open', mock.mock_open(read_data='test'))
    def test_read_yangcatalog_config(self):
        result = self.client.get('api/admin/yangcatalog-config')

        self.assertJsonResponse(result, 200, 'info', 'Success')
        self.assertJsonResponse(result, 200, 'data', 'test')

    @mock.patch('api.views.admin.open')
    def test_update_yangcatalog_config(self, mock_open: mock.MagicMock):
        mock.mock_open(mock_open)
        result = self.client.put('/api/admin/yangcatalog-config', json={'input': {'data': 'test'}})

        f = mock_open()
        f.write.assert_called_with('test')
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.is_json)

    @mock.patch('requests.post')
    @mock.patch('api.yangcatalog_api.app.load_config')
    @mock.patch('builtins.open')
    def test_update_yangcatalog_config_errors(
        self,
        mock_open: mock.MagicMock,
        mock_load_config: mock.MagicMock,
        mock_post: mock.MagicMock,
    ):
        mock.mock_open(mock_open)
        mock_load_config.side_effect = Exception
        mock_post.return_value.status_code = 404
        result = self.client.put('/api/admin/yangcatalog-config', json={'input': {'data': 'test'}})

        self.assertJsonResponse(result, 200, 'info', {'api': 'error loading data'})
        self.assertJsonResponse(result, 200, 'new-data', 'test')

    @mock.patch('os.walk')
    def test_get_log_files(self, mock_walk: mock.MagicMock):
        mock_walk.return_value = [('root/logs', [], ['test', 'test.log'])]
        result = self.client.get('api/admin/logs')

        self.assertJsonResponse(result, 200, 'info', 'Success')
        self.assertJsonResponse(result, 200, 'data', ['test'])

    @mock.patch('os.walk')
    def test_find_files(self, mock_walk: mock.MagicMock):
        mock_walk.return_value = iter((('/', (), ('thing.bad', 'badlog', 'good.log', 'good.log-more')),))
        result = tuple(admin.find_files('/', 'good.log*'))

        self.assertEqual(result, ('/good.log', '/good.log-more'))

    @mock.patch('os.path.getmtime')
    @mock.patch('api.views.admin.find_files')
    def test_filter_from_date(self, mock_find_files: mock.MagicMock, mock_getmtime: mock.MagicMock):
        mock_find_files.return_value = iter(('test1', 'test2', 'test3'))
        mock_getmtime.side_effect = (1, 2, 3)

        result = admin.filter_from_date(['logfile'], 2)

        self.assertEqual(result, ['test2', 'test3'])

    def test_filter_from_date_no_from_timestamp(self):
        result = admin.filter_from_date(['logfile'], None)

        self.assertEqual(result, [f'{app_config.d_logs}/logfile.log'])

    @mock.patch('builtins.open')
    def test_find_timestamp(self, mock_open: mock.MagicMock):
        mock.mock_open(mock_open, read_data='2000-01-01 00:00:00')
        result = admin.find_timestamp(
            'test',
            r'([12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]))',
            r'(?:[01]\d|2[0-3]):(?:[0-5]\d):(?:[0-5]\d)',
        )
        self.assertEqual(result, 946684800.0)

    @mock.patch('builtins.open')
    def test_find_timestamp_not_found(self, mock_open: mock.MagicMock):
        mock.mock_open(mock_open, read_data='test')
        result = admin.find_timestamp(
            'test',
            r'([12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]))',
            r'(?:[01]\d|2[0-3]):(?:[0-5]\d):(?:[0-5]\d)',
        )
        self.assertEqual(result, None)

    @mock.patch('builtins.open')
    def test_determine_formatting_false(self, mock_open: mock.MagicMock):
        mock.mock_open(mock_open, read_data='test')
        result = admin.determine_formatting(
            'test',
            r'([12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]))',
            r'(?:[01]\d|2[0-3]):(?:[0-5]\d):(?:[0-5]\d)',
        )

        self.assertFalse(result)

    @mock.patch('builtins.open')
    def test_determine_formatting_true(self, mock_open: mock.MagicMock):
        data = '2000-01-01 00:00:00 ERROR two words =>\n' * 2
        mock.mock_open(mock_open, read_data=data)
        result = admin.determine_formatting(
            'test',
            r'([12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]))',
            r'(?:[01]\d|2[0-3]):(?:[0-5]\d):(?:[0-5]\d)',
        )

        self.assertTrue(result)

    def test_generate_output(self):
        date_regex = r'([12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]))'
        time_regex = r'(?:[01]\d|2[0-3]):(?:[0-5]\d):(?:[0-5]\d)'
        with mock.patch('builtins.open', mock.mock_open(read_data=self.test_log_text)):
            result = admin.generate_output(False, ['test'], None, None, None, date_regex, time_regex)

        self.assertEqual(result, list(reversed(self.test_log_text.splitlines())))

    def test_generate_output_filter(self):
        filter = {
            'match-case': False,
            'match-words': True,
            'filter-out': 'deleting',
            'search-for': 'yangcatalog',
            'level': 'warning',
        }
        date_regex = r'([12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]))'
        time_regex = r'(?:[01]\d|2[0-3]):(?:[0-5]\d):(?:[0-5]\d)'
        with mock.patch('builtins.open', mock.mock_open(read_data=self.test_log_text)):
            result = admin.generate_output(True, ['test'], filter, 1609455600.0, 1640905200.0, date_regex, time_regex)

        self.assertEqual(
            result,
            ['2021-07-07 11:02:39 WARNING     admin.py   api => Getting yangcatalog log files - 298\nt'],
        )

    def test_generate_output_filter_match_case(self):
        filter = {
            'match-case': True,
            'match-words': True,
            'filter-out': 'Deleting',
            'search-for': 'yangcatalog',
            'level': 'warning',
        }
        date_regex = r'([12]\d{3}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01]))'
        time_regex = r'(?:[01]\d|2[0-3]):(?:[0-5]\d):(?:[0-5]\d)'
        with mock.patch('builtins.open', mock.mock_open(read_data=self.test_log_text)):
            result = admin.generate_output(True, ['test'], filter, 1609455600.0, 1640905200.0, date_regex, time_regex)

        self.assertEqual(
            result,
            ['2021-07-07 11:02:39 WARNING     admin.py   api => Getting yangcatalog log files - 298\nt'],
        )

    @mock.patch('api.views.admin.generate_output', mock.MagicMock(return_value=3 * ['test']))
    @mock.patch('api.views.admin.determine_formatting', mock.MagicMock(return_value=True))
    @mock.patch('api.views.admin.find_timestamp', mock.MagicMock(return_value=0))
    @mock.patch('api.views.admin.filter_from_date', mock.MagicMock())
    def test_get_logs(self):
        body = {'input': {'lines-per-page': 2, 'page': 2}}

        result = self.client.post('/api/admin/logs', json=body)

        meta = {
            'file-names': ['yang'],
            'from-date': 0,
            'to-date': (result.json or {}).get('meta', {}).get('to-date'),
            'lines-per-page': 2,
            'page': 2,
            'pages': 2,
            'filter': None,
            'format': True,
        }
        self.assertJsonResponse(result, 200, 'meta', meta)
        self.assertJsonResponse(result, 200, 'output', ['test'])

    def test_move_user(self):
        self.addCleanup(self.users.delete, self.uid, temp=False)
        body = {'id': self.uid, 'access-rights-sdo': 'test'}
        result = self.client.post('api/admin/move-user', json={'input': body})

        self.assertJsonResponse(result, 201, 'info', 'user successfully approved')
        self.assertJsonResponse(result, 201, 'data', body)
        self.assertTrue(self.users.is_approved(self.uid))

    def test_create_user(self):
        body = self.payloads_content['user']

        result = self.client.post('api/admin/users/temp', json=body)

        self.assertJsonResponse(result, 201, 'info', 'data successfully added to database')
        self.assertJsonResponse(result, 201, 'data', body['input'])
        data = result.json
        assert data
        self.assertIn('id', data)
        self.assertTrue(self.users.is_temp(data['id']))
        self.users.delete(data['id'], temp=True)

    def test_create_user_invalid_status(self):
        body = self.payloads_content['user']

        result = self.client.post('api/admin/users/fake', json=body)

        self.assertJsonResponse(result, 400, 'error', 'invalid status "fake", use only "temp" or "approved" allowed')

    def test_delete_user(self):
        result = self.client.delete(f'api/admin/users/temp/id/{self.uid}')

        self.assertJsonResponse(result, 200, 'info', f'id {self.uid} deleted successfully')
        self.assertFalse(self.users.is_temp(self.uid))

    def test_delete_user_invalid_status(self):
        result = self.client.delete(f'api/admin/users/fake/id/{self.uid}')

        self.assertJsonResponse(result, 400, 'error', 'invalid status "fake", use only "temp" or "approved" allowed')

    def test_delete_user_id_not_found(self):
        result = self.client.delete('api/admin/users/approved/id/24857629847625894258476')

        self.assertJsonResponse(result, 404, 'description', 'id 24857629847625894258476 not found with status approved')

    def test_update_user(self):
        body = deepcopy(self.payloads_content['user'])
        body['input']['username'] = 'jdoe'

        result = self.client.put(f'api/admin/users/temp/id/{self.uid}', json=body)

        self.assertJsonResponse(result, 200, 'info', f'ID {self.uid} updated successfully')
        self.assertEqual(self.users.get_field(self.uid, 'username'), 'jdoe')

    def test_update_user_invalid_status(self):
        result = self.client.put(f'api/admin/users/fake/id/{self.uid}')

        self.assertJsonResponse(result, 400, 'error', 'invalid status "fake", use only "temp" or "approved" allowed')

    def test_update_user_id_not_found(self):
        result = self.client.put('api/admin/users/approved/id/24857629847625894258476')

        self.assertJsonResponse(result, 404, 'description', 'id 24857629847625894258476 not found with status approved')

    def test_get_users(self):
        result = self.client.get('api/admin/users/temp')

        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.is_json)
        data = result.json
        self.assertTrue(isinstance(data, list))

    def test_get_script_details(self):
        result = self.client.get('api/admin/scripts/reviseSemver')

        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.is_json)
        data = result.json
        self.assertIn('data', data)

    def test_get_script_details_invalid_name(self):
        result = self.client.get('api/admin/scripts/invalid')

        self.assertJsonResponse(result, 400, 'description', '"invalid" is not valid script name')

    @mock.patch('api.views.admin.run_script.s')
    def test_run_script_with_args(self, run_script_mock: mock.MagicMock):
        run_script_mock.return_value.apply_async.return_value = mock.MagicMock(id=1)
        result = self.client.post('api/admin/scripts/populate', json={'input': 'test'})
        self.assertJsonResponse(result, 202, 'info', 'Verification successful')
        self.assertJsonResponse(result, 202, 'job-id', 1)
        self.assertJsonResponse(result, 202, 'arguments', ['parseAndPopulate', 'populate', 'test'])

    def test_run_script_with_args_invalid_name(self):
        result = self.client.post('api/admin/scripts/invalid')

        self.assertJsonResponse(result, 400, 'description', '"invalid" is not valid script name')

    def test_get_script_names(self):
        result = self.client.get('api/admin/scripts')

        self.assertJsonResponse(result, 200, 'info', 'Success')
        data = result.json
        self.assertIn('data', data)
        self.assertIsInstance(data['data'], list)

    def test_get_disk_usage(self):
        result = self.client.get('api/admin/disk-usage')

        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.is_json)
        data = result.json
        self.assertIn('data', data)
        self.assertIn('total', data['data'])
        self.assertIn('used', data['data'])
        self.assertIn('free', data['data'])
        self.assertIn('info', data)
        self.assertEqual(data['info'], 'Success')

    @mock.patch('redisConnections.redisConnection.RedisConnection.get_module')
    def test_get_redis_module_existing_module(self, mock_get_module):
        mock_get_module.return_value = '{"name": "test_module"}'
        response = self.client.get('/api/admin/module/test_module@2023-10-20/test_organization')
        self.assertEqual(response.status_code, 200)
        mock_get_module.assert_called_once_with('test_module@2023-10-20/test_organization')

        # Checking if payload looks as expected
        response_data = response.get_json()
        self.assertIn('name', response_data)
        self.assertEqual(response_data['name'], 'test_module')

    @mock.patch('redisConnections.redisConnection.RedisConnection.get_module')
    def test_get_redis_module_non_existing_module(self, mock_get_module):
        mock_get_module.return_value = '{}'
        response = self.client.get('/api/admin/module/test_module@2023-10-20/test_organization')
        self.assertEqual(response.status_code, 404)
        mock_get_module.assert_called_once_with('test_module@2023-10-20/test_organization')

        # Checking if payload looks as expected
        response_data = response.get_json()
        self.assertIn('test_module@2023-10-20/test_organization', response_data)
        self.assertIn('info', response_data['test_module@2023-10-20/test_organization'])
        self.assertEqual(response_data['test_module@2023-10-20/test_organization']['info'], 'Module does not exist.')

    @mock.patch('redisConnections.redisConnection.RedisConnection.get_module')
    def test_get_redis_module_internal_server_error(self, mock_get_module):
        mock_get_module.side_effect = Exception('Internal server error occured.')
        response = self.client.get('/api/admin/module/test_module@2023-10-20/test_organization')
        self.assertEqual(response.status_code, 500)
        mock_get_module.assert_called_once_with('test_module@2023-10-20/test_organization')

    @mock.patch('redisConnections.redisConnection.RedisConnection.get_module')
    @mock.patch('redisConnections.redisConnection.RedisConnection.set_module')
    def test_update_redis_module_valid_data(self, mock_set_module, mock_get_module):
        with open(os.path.join(self.resources_path, 'yang-catalog@2018-04-03.json'), 'r') as f:
            modules_data = json.load(f)
        mock_get_module.return_value = '{"name": "test_module"}'
        response = self.client.put('/api/admin/module/test_module@2023-10-20/test_organization', json=modules_data)
        self.assertEqual(response.status_code, 200)
        mock_get_module.assert_called_once_with('test_module@2023-10-20/test_organization')
        mock_set_module.assert_called_once_with(modules_data, 'test_module@2023-10-20/test_organization')

        # Checking if payload looks as expected
        response_data = response.get_json()
        self.assertIn('message', response_data)
        self.assertEqual(
            response_data['message'],
            'Module test_module@2023-10-20/test_organization updated successfully.',
        )


if __name__ == '__main__':
    unittest.main()
