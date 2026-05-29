"""Application configuration for the Flask ``hello_world`` service.

This module externalizes the configuration that was hard-coded in the legacy
Node.js implementation (``server.js``) into class-based, environment-driven
settings. In the original server the bind address and port were fixed
constants::

    const hostname = '127.0.0.1';   // server.js:L3
    const port = 3000;              // server.js:L4

To preserve byte-for-byte behavioral parity with that server, the defaults
below reproduce the loopback-only binding ``127.0.0.1:3000`` exactly while
making every value overridable through the environment (the "environment
config" capability mandated by the project rule).

Design notes
------------
* **Class-based config objects.** :class:`Config` holds the base settings;
  :class:`DevelopmentConfig` and :class:`ProductionConfig` specialize the
  ``DEBUG`` flag. This is the canonical Flask configuration pattern and
  integrates directly with :meth:`flask.Config.from_object`.
* **UPPERCASE attributes.** Flask's ``from_object`` loads *only* uppercase
  attributes (including inherited ones) into ``app.config``. The development
  launcher (``run.py``) additionally reads ``Config.HOST`` / ``Config.PORT`` as
  plain class attributes. Both consumers therefore require these names to be
  uppercase, so they must never be renamed to lowercase.
* **``load_dotenv()`` at import time.** Values declared in a local ``.env``
  file are loaded into ``os.environ`` *before* the classes read them.
  :func:`~dotenv.load_dotenv` is a no-op when ``.env`` is absent and, with its
  default ``override=False``, never clobbers variables already present in the
  real process environment -- so an explicit ``HOST=0.0.0.0`` shell export
  still takes precedence over the ``.env`` value.
* **No Flask import.** This module is intentionally framework-free to keep it a
  pure, side-effect-light configuration source and to avoid any circular import
  with the application factory in ``app/__init__.py``.
"""

import os

from dotenv import load_dotenv

# Load variables declared in a local ``.env`` file into ``os.environ`` *before*
# the configuration classes below read them. This is safe when no ``.env`` file
# exists (python-dotenv simply does nothing) and, because the default is
# ``override=False``, it never overwrites variables that are already set in the
# surrounding process environment.
load_dotenv()


class Config:
    """Base configuration shared by every environment.

    The defaults intentionally mirror the legacy Node.js server so that, with
    no environment overrides in place, the Flask application binds to the exact
    same loopback address and port the original used (``127.0.0.1:3000``).

    Attributes:
        HOST (str): Network interface to bind. Defaults to ``'127.0.0.1'`` to
            preserve the legacy loopback-only binding (``server.js:L3``). Set
            the ``HOST`` environment variable (e.g. ``'0.0.0.0'``) to override.
        PORT (int): TCP port to listen on, coerced to :class:`int` because
            environment variables are always strings. Defaults to ``3000``
            (``server.js:L4``).
        LOG_LEVEL (str): Logging verbosity name consumed by
            ``app/logging_config.py`` (e.g. ``'DEBUG'``, ``'INFO'``,
            ``'WARNING'``). Defaults to ``'INFO'``.
        FLASK_ENV (str): Active environment name (``'development'`` or
            ``'production'``) used by :func:`get_config` to select a
            configuration class. Defaults to ``'development'``.
    """

    # Bind to the loopback interface by default (legacy parity, server.js:L3).
    HOST = os.environ.get('HOST', '127.0.0.1')

    # Environment variables arrive as strings; coerce to ``int`` so consumers
    # such as ``run.py`` and Gunicorn receive a real integer port
    # (legacy parity, server.js:L4).
    PORT = int(os.environ.get('PORT', '3000'))

    # Default logging verbosity; consumed by the logging configuration module.
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')

    # Active environment selector; drives :func:`get_config` below.
    FLASK_ENV = os.environ.get('FLASK_ENV', 'development')


class DevelopmentConfig(Config):
    """Development configuration.

    Enables Flask debug mode while inheriting the loopback-preserving
    ``HOST`` / ``PORT`` / ``LOG_LEVEL`` / ``FLASK_ENV`` values from
    :class:`Config`.
    """

    DEBUG = True


class ProductionConfig(Config):
    """Production configuration.

    Disables Flask debug mode. The bind address still defaults to the legacy
    loopback ``127.0.0.1``; a deployment may widen it (e.g. ``HOST=0.0.0.0``)
    purely through the environment. The default is deliberately *not*
    hard-coded to ``0.0.0.0`` here so that the legacy loopback behavior is
    preserved out of the box (AAP 0.6.5).
    """

    DEBUG = False


# Mapping from ``FLASK_ENV`` name to the concrete configuration class. Consumed
# by :func:`get_config` and available for callers that need to resolve a config
# class by name directly.
config_by_name = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
}


def get_config():
    """Return the configuration class selected by ``FLASK_ENV``.

    The application factory (``app/__init__.py``) calls this when no explicit
    configuration class is supplied, then passes the result to
    :meth:`flask.Config.from_object`. Any unrecognized ``FLASK_ENV`` value
    falls back to :class:`DevelopmentConfig`, matching the base default and
    ensuring the loopback-preserving settings always apply.

    Returns:
        type: The :class:`Config` subclass corresponding to the current
        ``FLASK_ENV`` value (defaults to :class:`DevelopmentConfig`).
    """

    return config_by_name.get(
        os.environ.get('FLASK_ENV', 'development'),
        DevelopmentConfig,
    )
