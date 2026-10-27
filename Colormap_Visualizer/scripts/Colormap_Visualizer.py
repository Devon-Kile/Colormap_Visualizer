# -*- coding: utf-8 -*-

import gom
import os
import subprocess
import numpy as np
from library import export_colormap_visualizer


def generate_html(colormap, out_path):
	"""Recalculate one inspection element, extract its arrays, and export HTML.

	The template expects stage-first arrays. Meshes include triangle indices;
	point clouds omit triangles and use result_dimension as their scalar source
	when GOM does not provide usable data.scalar_value values.
	"""
	# Recalculate first so the arrays and scalar values reflect the current
	# project state rather than a potentially outdated inspection result.
	gom.script.sys.recalculate_elements(elements=[colormap])

	# Point-cloud result_dimension entries may be deviation objects or raw
	# numbers. Preserve missing values as NaN so the viewer can skip them.
	def parse_deviation(item):
		val = item.deviation if hasattr(item, 'deviation') else item
		return np.nan if val is None else float(val)

	# Coordinates and normals are stage-first in GOM. Normals are retained for
	# meshes; the point renderer does not require them.
	coordinates = np.array(colormap.data.coordinate)
	normals = np.array(colormap.data.normal)

	# Triangle access can fail even when the attribute exists on a GOM data
	# object. Treat empty or inaccessible triangle data as a point cloud.
	has_mesh = False
	if hasattr(colormap.data, 'triangle'):
		try:
			tri_check = np.array(colormap.data.triangle)
			if tri_check is not None and tri_check.size > 0:
				has_mesh = True
		except (RuntimeError, TypeError):
			has_mesh = False

	triangles = np.array(colormap.data.triangle) if has_mesh else None

	# Prefer the stage-aware scalar array for mesh comparisons, surface
	# components, and vector fields. Some discrete point-cloud comparisons
	# expose no usable scalar_value array, so those fall back below.
	has_valid_data_scalars = False
	if hasattr(colormap.data, 'scalar_value') and colormap.data.scalar_value is not None:
		try:
			sv_check = np.array(colormap.data.scalar_value)
			if sv_check.size > 0 and not np.all(np.isnan(sv_check)):
				scalar_values = sv_check
				has_valid_data_scalars = True
		except (RuntimeError, TypeError):
			has_valid_data_scalars = False

	# Fallback for discrete point clouds: result_dimension is a sequence of GOM
	# deviation values. Reshape the single-stage values to (1, N, 1), matching
	# the archive layout expected by the viewer.
	if not has_valid_data_scalars:
		raw_scalars = np.array(
			[parse_deviation(item) for item in colormap.result_dimension],
			dtype=np.float64
		)
		# Reshape (N,) -> (1, N, 1) to match stage layout of colormap.data arrays
		scalar_values = raw_scalars[np.newaxis, :, np.newaxis]

	# Pass the type as a plain string because the GOM ObjectType wrapper is not
	# JSON serializable. Scalar values are stored in mm; the viewer can convert
	# them for display without changing the embedded source data.
	export_colormap_visualizer(
		coordinates,
		normals,
		scalar_values,
		triangles,
		out_path,
		colormap_type=str(colormap.type),
	)


# Derive the output name from the actual project filename, regardless of
# whether ZEISS uses .zinspect, .ginspect, .gcorrelate, or another extension.
def output_path_for(colormap=None):
	project_path = gom.app.project.project_file
	project_dir, project_filename = os.path.split(project_path)
	project_stem, _project_extension = os.path.splitext(project_filename)

	# Add the selected element's name when available. splitext removes only the
	# final project extension and leaves earlier dots in the project name intact.
	colormap_name = getattr(colormap, 'name', None) if colormap is not None else None
	if colormap_name:
		project_stem += f'_{colormap_name}'

	return os.path.join(project_dir, project_stem + '.html')


DIALOG = gom.script.sys.create_user_defined_dialog(file='dialog.gdlg')

def dialog_event_handler(widget):
	if widget == DIALOG.colormap:
		# Keep the suggested filename synchronized with the current selection.
		DIALOG.file = output_path_for(DIALOG.colormap.value)
			
	if widget == DIALOG.button:
		# Create the destination directory if the dialog path points to one.
		out_dir = os.path.dirname(DIALOG.file.value)
		if out_dir:
			os.makedirs(out_dir, exist_ok=True)
		DIALOG.log.text += f'Generating HTML Colormap Visualizer for \n{os.path.basename(DIALOG.file.value)}\n'

		try:
			# Export errors are reported in the dialog log and stop this button
			# action, while clipboard failures below do not undo a successful file.
			gom.script.sys.recalculate_project (with_reports=False)			
			generate_html(DIALOG.colormap.value, DIALOG.file.value)
			DIALOG.log.text += 'HTML Colormap Visualizer generated successfully.\n'
		except Exception as e:
			DIALOG.log.text += f'Error: {e}\n'
			return

		# Copy the output directory through clip's stdin to avoid shell quoting
		# problems with spaces, ampersands, or other path characters.
		folder_path = os.path.dirname(os.path.abspath(DIALOG.file.value))
		try:
			subprocess.run(
				['clip'],
				input=folder_path,
				text=True,
				check=True,
			)
			DIALOG.log.text += f'Folder path copied to clipboard\n'
		except Exception as clipboard_error:
			DIALOG.log.text += f'HTML was generated, but the folder path could not be copied: {clipboard_error}\n'
	
		
	
def element_filter(element) -> bool:
	"""Allow only inspection element types supported by the exporter."""
	try:
		if element.type in (
			'surface_comparison_actual_mesh',
			'surface_comparison',
			'inspection_surface_component',
			'inspection_vector_field'
		):
			return True
	except Exception:
		pass
	return False

DIALOG.handler = dialog_event_handler
DIALOG.colormap.filter = element_filter

# Set a useful initial suggestion before the user opens the dialog. The event
# handler updates it again if the user changes the selected colormap.
DIALOG.file = output_path_for(DIALOG.colormap.value)

# The result is left to ZEISS INSPECT's dialog framework; exporting happens
# from the explicit button handler above.
RESULT = gom.script.sys.show_user_defined_dialog(dialog=DIALOG)

