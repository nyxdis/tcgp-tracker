"""Tracker app base view configuration."""

# Expose all views from submodules for backward compatibility.
from .cards import *
from .friends import *
from .health import health_check
from .users import *
