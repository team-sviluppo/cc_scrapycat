from pydantic import BaseModel
from cat.mad_hatter.decorators import plugin
from enum import Enum


# Plugin settings
class PluginSettings(BaseModel):
    ingest_pdf: bool = False
    skip_get_params: bool = False
    max_depth: int


# hook to give the cat settings
@plugin
def settings_schema():
    return PluginSettings.schema()
