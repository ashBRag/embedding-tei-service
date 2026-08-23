"""Reusable, environment-aware settings base for pydantic-settings.

Self-contained: this folder has no dependency on any other libs/* package,
so it can be copied into another project (or split into its own repo) as-is.
"""

from libs.config.base import BaseAppSettings, Environment, get_environment, resolve_env_file

__all__ = ["BaseAppSettings", "Environment", "get_environment", "resolve_env_file"]
