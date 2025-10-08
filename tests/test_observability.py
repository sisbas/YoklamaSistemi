import json
import os
import sys
from pathlib import Path
from typing import Generator

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app import create_app
from correlation_id_middleware import HEADER_NAME
from models import db


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Generator:
    monkeypatch.setenv('CLIENT_LOG_RATE_LIMIT', '2')
    monkeypatch.setenv('CLIENT_LOG_WINDOW_SECONDS', '60')
    monkeypatch.setenv('REQUEST_LOG_SAMPLE_RATE', '1')
    os.environ.pop('DATABASE_URL', None)
    application = create_app()
    application.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SERVER_NAME='testserver',
    )
    with application.app_context():
        db.create_all()
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


def test_health_endpoint(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.get_json() == {'status': 'ok'}


def test_request_id_propagation(client):
    response = client.get('/health', headers={HEADER_NAME: 'test-id-123'})
    assert response.headers.get(HEADER_NAME) == 'test-id-123'


def test_error_handler_returns_problem_details(client):
    response = client.get('/api/students')
    data = response.get_json()
    assert response.status_code == 400
    assert data['status'] == 400
    assert data['title']
    assert data['detail']
    assert data['request_id']


def test_client_logs_ingestion_and_rate_limit(client):
    payload = {'level': 'error', 'message': 'client failure'}
    accepted = client.post('/client-logs', data=json.dumps(payload), content_type='application/json')
    assert accepted.status_code == 202
    second = client.post('/client-logs', data=json.dumps(payload), content_type='application/json')
    assert second.status_code == 202
    third = client.post('/client-logs', data=json.dumps(payload), content_type='application/json')
    assert third.status_code == 429
    data = third.get_json()
    assert data['status'] == 429
