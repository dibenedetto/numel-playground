from __future__ import annotations

import asyncio
import os
import shutil
import sys
import unittest
import uuid
from pathlib import Path

import httpx


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SERVICE_ROOT = PROJECT_ROOT / 'services' / 'identity_django'
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))


class DjangoIdentityServiceTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._root = PROJECT_ROOT / 'storage' / '_test_runs' / f'identity_django_{uuid.uuid4().hex[:8]}'
        cls._root.mkdir(parents=True, exist_ok=True)
        cls._db_path = (cls._root / 'identity.sqlite3').resolve()
        cls._previous_env = {
            'DJANGO_SETTINGS_MODULE': os.environ.get('DJANGO_SETTINGS_MODULE'),
            'DATABASE_URL': os.environ.get('DATABASE_URL'),
            'NUMEL_IDENTITY_ALLOWED_HOSTS': os.environ.get('NUMEL_IDENTITY_ALLOWED_HOSTS'),
            'NUMEL_IDENTITY_SECRET_KEY': os.environ.get('NUMEL_IDENTITY_SECRET_KEY'),
        }
        os.environ['DJANGO_SETTINGS_MODULE'] = 'identity_service.settings'
        os.environ['DATABASE_URL'] = f'sqlite:///{cls._db_path.as_posix()}'
        os.environ['NUMEL_IDENTITY_ALLOWED_HOSTS'] = '*'
        os.environ['NUMEL_IDENTITY_SECRET_KEY'] = 'test-secret-key'

        import django
        django.setup()

        from django.core.management import call_command
        call_command('migrate', verbosity=0)

        from identity_service.asgi import application
        cls._application = application

    @classmethod
    def tearDownClass(cls) -> None:
        for key, value in cls._previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(cls._root, ignore_errors=True)
        super().tearDownClass()

    async def asyncSetUp(self) -> None:
        from django.core.management import call_command
        await asyncio.to_thread(call_command, 'flush', verbosity=0, interactive=False)
        self._client = httpx.AsyncClient(
            base_url='http://identity.test',
            transport=httpx.ASGITransport(app=self._application),
        )

    async def asyncTearDown(self) -> None:
        await self._client.aclose()

    async def test_identity_service_matches_platform_contract(self) -> None:
        status = await self._client.post('/api/platform/auth/status', json={})
        self.assertEqual(status.status_code, 200)
        self.assertFalse(status.json()['has_users'])

        created = await self._client.post(
            '/api/platform/users/create',
            json={'username': 'alice', 'email': 'alice@local', 'password': 'pass1234'},
        )
        self.assertEqual(created.status_code, 200)
        user = created.json()['user']
        self.assertEqual(user['role'], 'admin')
        user_id = user['id']

        login = await self._client.post(
            '/api/platform/auth/login',
            json={'username': 'alice', 'password': 'pass1234'},
        )
        self.assertEqual(login.status_code, 200)
        token = login.json()['token']

        authenticated = await self._client.post(
            '/api/platform/auth/authenticate',
            headers={'Authorization': f'Bearer {token}'},
            json={'token': token},
        )
        self.assertEqual(authenticated.status_code, 200)
        self.assertEqual(authenticated.json()['user']['username'], 'alice')

        fetched = await self._client.post(f'/api/platform/users/{user_id}', json={})
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.json()['profile']['display_name'], 'alice')
        self.assertEqual(fetched.json()['quota']['max_spaces'], 50)

        profile = await self._client.post(
            f'/api/platform/users/{user_id}/profile',
            json={'bio': 'hello'},
        )
        self.assertEqual(profile.status_code, 200)
        self.assertEqual(profile.json()['profile']['bio'], 'hello')

        quota = await self._client.post(
            f'/api/platform/users/{user_id}/quota',
            json={'max_spaces': 99},
        )
        self.assertEqual(quota.status_code, 200)
        self.assertEqual(quota.json()['quota']['max_spaces'], 99)

        changed = await self._client.post(
            '/api/platform/auth/change-password',
            json={'user_id': user_id, 'current_password': 'pass1234', 'new_password': 'pass5678'},
        )
        self.assertEqual(changed.status_code, 200)
        self.assertTrue(changed.json()['ok'])

        old_login = await self._client.post(
            '/api/platform/auth/login',
            json={'username': 'alice', 'password': 'pass1234'},
        )
        self.assertEqual(old_login.status_code, 401)

        new_login = await self._client.post(
            '/api/platform/auth/login',
            json={'username': 'alice', 'password': 'pass5678'},
        )
        self.assertEqual(new_login.status_code, 200)

        listed = await self._client.post('/api/platform/users/list', json={'offset': 0, 'limit': 10, 'active_only': True})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()['users']), 1)

        deleted = await self._client.post(f'/api/platform/users/{user_id}/delete', json={})
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()['ok'])
