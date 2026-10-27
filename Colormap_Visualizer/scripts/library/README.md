# Colormap Visualizer exporter

This project exports ZEISS INSPECT colormaps as standalone HTML viewers. For a ZEISS INSPECT add-on, package the files with this layout:

```text
scripts/
  Colormap_Visualizer.py
  library/
    __init__.py
    export_colormap_visualizer.py
    standalone_template.html
```

Keep the three `library` files together. The exporter loads the HTML through
ZEISS's `gom.Resource` API using the path inside the add-on
`scripts/library/standalone_template.html`. This works both while editing an
unpacked add-on and after finalizing it as a zipped `.addon`; `Path(__file__)`
cannot reliably locate non-Python resources in a finalized add-on. The Python
exporter requires the ZEISS `gom` runtime, its add-on API, and NumPy. The
recipient of the generated HTML does not need any of these.

```python
import gom
import numpy as np
from library import export_colormap_visualizer

colormap = gom.app.project.inspection['Surface comparison 1']
coordinates = np.array(colormap.data.coordinate)
normals = np.array(colormap.data.normal)
scalar_values = np.array(colormap.data.scalar_value)
triangles = np.array(colormap.data.triangle)

export_colormap_visualizer(
    coordinates,
    normals,
    scalar_values,
    triangles,
    r"S:\Zeiss Inspect\Shared Apps\surface_comparison.html",
    colormap_type=str(colormap.type),
)
```

For a discrete point cloud comparison, the triangle data is not available. Pass
`None` (or omit the triangle argument) and provide the HTML path as the fourth
argument. The viewer will render colored points and show a Small/Medium/Large
point size selector. ZEISS may return deviation objects or `None` values from
`colormap.result_dimension`; convert each value safely before exporting:

```python
def parse_deviation(item):
    value = item.deviation if hasattr(item, "deviation") else item
    return np.nan if value is None else float(value)

coordinates = np.array(colormap.data.coordinate)
normals = np.array(colormap.data.normal)
raw_scalars = np.array(
    [parse_deviation(item) for item in colormap.result_dimension],
    dtype=np.float64,
)
scalar_values = raw_scalars[np.newaxis, :, np.newaxis]

export_colormap_visualizer(
    coordinates,
    normals,
    scalar_values,
    None,
    r"S:\Zeiss Inspect\Shared Apps\point_comparison.html",
    colormap_type=str(colormap.type),
)

# Equivalent call when triangles are omitted:
export_colormap_visualizer(
    coordinates,
    normals,
    scalar_values,
    r"S:\Zeiss Inspect\Shared Apps\point_comparison.html",
    colormap_type=str(colormap.type),
)
```

## ZEISS INSPECT dialog script

`Colormap_Visualizer_Zeiss_Script_for_ref.py` is an example integration script
for a ZEISS user-defined dialog. It filters the selectable elements, recalculates
the chosen colormap, extracts its arrays, and generates the HTML when the user
clicks the dialog's export button. The selected output folder is then copied to
the clipboard using Windows `clip`; if clipboard copying fails, the log reports
that separately while preserving the successful HTML export.

The integration script passes `str(colormap.type)` to the exporter. Pass this
string form when calling the exporter from ZEISS because ZEISS's `ObjectType`
instances are not JSON serializable.

Arrays with more than one entry on axis 0 show a stage timeline. Shorter
sequences use individual stage buttons; longer sequences use a draggable ruler.
Deviation labels stay attached to their picked point or mesh location and
update their value when the stage changes. Surface comparison labels are
reprojected to the closest surface point on each stage because the mesh vertex
and triangle indices can change. Surface-component and vector-field labels use
their corresponding point index. Back-facing mesh triangles use the ZEISS
teal color (RGB 77, 153, 153). For `inspection_vector_field`, the
viewer also shows displacement-vector controls. Vectors are derived from the
coordinates relative to stage 0, and only that colormap type gets the vector
display and scaling controls.

The function creates one self-contained HTML file. The recipient can open it in a browser without installing software, running a server, or connecting to the network. It includes the current viewer controls and deviation labels, but does not allow loading another `.npz` file.

Length-valued scalar data is archived in millimeters. The legend unit selector
lets viewers switch between millimeters and inches; values, labels, and color
limits are converted for display while the embedded source values remain
unchanged. Strain values are not length values, and their unit handling is a
known limitation below.
While editing a legend limit, use the mouse wheel to adjust it in 0.001
increments. Press Esc or right-click to finish placing deviation labels.

## Known limitations

- Discrete point-cloud comparisons may not provide `data.scalar_value`, so the
  ZEISS script currently falls back to `result_dimension`. That fallback
  produces one stage; trend projects with multi-stage point clouds need
  stage-aware scalar extraction to provide correct values throughout the
  timeline.
- The viewer currently assumes scalar values are lengths in millimeters and
  provides an mm/in switch. Surface-component strain values may instead be
  dimensionless percentages, so their current legend unit and conversion are
  not correct. Scalar-unit metadata (possibly from a ZEISS scalar-type field)
  needs to be investigated before strain colormaps can be labeled correctly.

