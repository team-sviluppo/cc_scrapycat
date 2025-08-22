from pydantic import BaseModel
from cat.mad_hatter.decorators import plugin
from enum import Enum


# Plugin settings
class PluginSettings(BaseModel):
    ingest_pdf: bool = False
    skip_get_params: bool = False
    max_depth: int = 0
    max_pages: int = -1
    allowed_extra_roots: str = ""  # Comma-separated list of allowed root URLs


# hook to give the cat settings
@plugin
def settings_schema():
    return PluginSettings.schema()
