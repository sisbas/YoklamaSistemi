"""Application configuration module.

This module reads environment variables to configure the Flask application and
database. When deployed on Heroku the platform provides a ``DATABASE_URL``
environment variable that points to a Postgres database. Recent versions of
SQLAlchemy expect the URL to start with ``postgresql://`` rather than
``postgres://``. The code below normalises the URL accordingly. This fix is
recommended by multiple deployment guides and avoids connection errors when
connecting to Heroku Postgres:contentReference[oaicite:0]{index=0}. The module also
loads any variables defined in a local ``.env`` file when running locally.

"""

import os
from dotenv import load_dotenv


class Config:
    """Base configuration class.

    SQLAlchemy and other extensions read their configuration from this class.
    The :class:`~flask_sqlalchemy.SQLAlchemy` instance will use the
    ``SQLALCHEMY_DATABASE_URI`` attribute to connect to the database. If no
    database URL is provided the application falls back to a local SQLite
    database so the app still runs in development.
    """

    # Load environment variables from a .env file if present. This is useful
    # during local development; on Heroku variables are set via ``heroku config``.
    load_dotenv()

    # Secret key used by Flask for session signing and CSRF protection. This
    # should be set to a random value in production and never committed to
    # version control. If undefined a default is used for development.
    SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-secret-in-prod')

    # Pull the database URL from the environment. Heroku uses the ``DATABASE_URL``
    # variable to provide the connection string. Normalise the prefix for
    # SQLAlchemy compatibility as recommended by the Heroku and Flask
    # communities:contentReference[oaicite:1]{index=1}. If no URL is provided fall back
    # to a local SQLite database stored in the project directory.
    _db_url = os.environ.get('DATABASE_URL', '')
    if _db_url.startswith('postgres://'):
        # Heroku used to supply URLs beginning with ``postgres://``. Replace
        # this prefix with ``postgresql://`` so SQLAlchemy recognises the
        # dialect. Only replace the first occurrence to avoid touching paths
        # that may legitimately contain the substring.
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    SQLALCHEMY_DATABASE_URI = _db_url or 'sqlite:///attendance.db'

    # Disable the SQLAlchemy event system to reduce overhead. It can safely be
    # enabled if your application requires change tracking.
    SQLALCHEMY_TRACK_MODIFICATIONS = False
