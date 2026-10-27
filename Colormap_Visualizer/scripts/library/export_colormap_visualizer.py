"""Create a self-contained HTML colormap viewer for sharing from ZEISS INSPECT.

The HTML viewer embeds the compressed arrays and has no runtime dependencies on
Python, a web server, external files, or a network connection.
"""

import base64
import json
from io import BytesIO
from pathlib import Path

import gom
import gom.api.addons
import numpy as np


# The template is packaged as an add-on resource, not a normal Python file.
# Resource lookup works both while editing the unpacked add-on and after
# finalization, when the add-on is stored as a ZIP archive.
_TEMPLATE_RESOURCE_PATH = "scripts/library/standalone_template.html"
_DATA_MARKER = "@@EMBEDDED_NPZ_BASE64@@"
_TYPE_MARKER = 'const exportedColormapType="";'


def _read_template():
	"""Read and decode the HTML template from the active ZEISS add-on."""
	# Resolve the active add-on at runtime. Do not hard-code its UUID, since
	# that changes when an add-on is copied or installed under another identity.
	addon = gom.api.addons.get_current_addon()
	if addon is None:
		raise RuntimeError(
			"Could not determine the current add-on, so the viewer template "
			"cannot be located."
		)

	# A qualified resource path starts with ':' and uses the add-on UUID as
	# its root, followed by the path inside the packaged add-on.
	resource_name = f":{addon.get_id()}/{_TEMPLATE_RESOURCE_PATH}"
	resource = gom.Resource(resource_name)
	if not resource.exists():
		raise FileNotFoundError(
			f"Standalone viewer template not found: {resource_name}. "
			"Make sure standalone_template.html is packaged in "
			"scripts/library."
		)

	# Resource reads may hold a shared-memory handle. Close it even if reading
	# raises, then decode the bytes as UTF-8 for safe marker replacement.
	try:
		with resource.open() as handle:
			data = handle.read()
	finally:
		resource.close()
	return bytes(data).decode("utf-8")


def export_colormap_visualizer(
	coordinate,
	normal,
	scalar_value,
	triangle=None,
	output_filepath=None,
	colormap_type=None,
):
	"""Write ZEISS colormap arrays to one standalone HTML viewer.

	Args:
		coordinate: Vertex coordinate array, shaped ``(stages, N, 3)``.
		normal: Vertex normal array, shaped ``(stages, N, 3)``.
		scalar_value: Deviation array, shaped ``(stages, N, 1)``.
		triangle: Optional triangle index array, shaped ``(stages, M, 3)``.
			Omit it or pass ``None`` for a discrete point cloud.
		output_filepath: Destination path for the generated ``.html`` file.
		colormap_type: Optional string type identifier. Pass
			``str(colormap.type)`` from ZEISS; ``"inspection_vector_field"``
			enables displacement-vector controls.
	Returns:
		The destination path as a string.
	"""
	# Keep the original four-positional-argument call convenient for point
	# clouds: (coordinate, normal, scalar_value, output_filepath). In that
	# calling form, the fourth argument arrives in ``triangle``.
	if output_filepath is None:
		output_filepath = triangle
		triangle = None
	if output_filepath is None:
		raise TypeError("output_filepath is required")

	output_path = Path(output_filepath)
	if output_path.suffix.lower() != ".html":
		raise ValueError("output_filepath must end in .html")

	# Read and validate the template before compressing potentially large
	# arrays. This fails early if the add-on resource is missing or stale.
	html = _read_template()
	if html.count(_DATA_MARKER) != 1 or html.count(_TYPE_MARKER) != 1:
		raise ValueError("Standalone viewer template has invalid dataset metadata markers.")

	# Build the same compressed NPZ structure used by the input workflow.
	# Omitting triangle entirely identifies a discrete point cloud to the
	# browser-side renderer.
	archive = BytesIO()
	arrays = {
		"coordinate": np.asarray(coordinate),
		"normal": np.asarray(normal),
		"scalar_value": np.asarray(scalar_value),
	}
	if triangle is not None:
		triangle_array = np.asarray(triangle)
		if triangle_array.size:
			arrays["triangle"] = triangle_array
	np.savez_compressed(archive, **arrays)
	# Base64 lets the archive travel inside a single HTML file without an
	# adjacent data file, server, or network dependency.
	encoded = base64.b64encode(archive.getvalue()).decode("ascii")

	# Embed data and the colormap type as valid JavaScript literals. JSON
	# encoding safely quotes ZEISS element-type strings.
	html = html.replace(_DATA_MARKER, encoded)
	html = html.replace(
		_TYPE_MARKER,
		f"const exportedColormapType={json.dumps(colormap_type)};",
	)
	# Create missing output folders before writing the standalone page.
	output_path.parent.mkdir(parents=True, exist_ok=True)
	output_path.write_text(html, encoding="utf-8")
	return str(output_path)
