"""Public package interface for the ZEISS INSPECT colormap exporter.

Keeping the import here lets ZEISS scripts use the short form
``from library import export_colormap_visualizer``.
"""

# Re-export the implementation function from the package root for convenient
# access by ZEISS scripts and other Python callers.
from .export_colormap_visualizer import export_colormap_visualizer

# Limit the documented/public package API to this supported entry point.
__all__ = ["export_colormap_visualizer"]

