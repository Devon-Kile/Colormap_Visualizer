# Colormap Visualizer — AI / Developer Handoff

## Purpose of this document

This document describes the current ZEISS INSPECT colormap exporter and the
standalone HTML viewer. Use it as working context when continuing development
in a fresh AI conversation or handing the project to another developer.

## 1. Executive summary

The project exports a ZEISS INSPECT inspection colormap into a single portable
HTML file. A ZEISS Python script reads the selected inspection element through
the `gom` API, converts its data to NumPy arrays, and calls the Python package
function `export_colormap_visualizer()`. The exporter stores the arrays in a
compressed NumPy `.npz` archive in memory, base64-encodes that archive, and
embeds it in `standalone_template.html`.

The recipient opens the resulting HTML in a modern browser. The page works
offline, needs no Python installation, server, adjacent data file, network
connection, or browser extension, and offers an interactive 3D view intended
to resemble the ZEISS INSPECT colormap experience.

The visualizer supports mesh and discrete point-cloud colormaps, multiple
stages, deviation labels, editable legend limits, mm/in display units, and
vector visualization for inspection vector fields. It is an exporter and
viewer, not a live connection to ZEISS: after export, the HTML contains a
snapshot of the arrays passed to it.

## 2. Handoff package and file architecture

The intended `.addon` deployment layout is:

```text
scripts/
  Colormap_Visualizer.py                # ZEISS INSPECT script / dialog entry point
  library/
    __init__.py                          # Public package export
    export_colormap_visualizer.py        # Python HTML generator
    standalone_template.html             # Self-contained browser viewer template
README.md                                # Installation and usage notes
prompt_for_ai.md                         # This context handoff
```

The ZEISS integration script imports the package with:

```python
from library import export_colormap_visualizer
```

Keep the three files in `scripts/library/` together inside the add-on. The
exporter reads the HTML through ZEISS's resource API, so the resource must be
packaged at `scripts/library/standalone_template.html`. The example dialog script also calls
`gom.script.sys.create_user_defined_dialog(file='dialog.gdlg')`; the dialog
resource must be available to ZEISS INSPECT wherever that script is installed
or configured. It is an INSPECT UI resource, not part of the HTML runtime.

### `library/__init__.py`

This is the public API shim. It imports `export_colormap_visualizer` from the
implementation module and lists that function in `__all__`. This allows callers
to use the stable, short import `from library import export_colormap_visualizer`
without importing internal implementation details.

### `Colormap_Visualizer.py` (currently represented by the reference script)

The supplied workspace script is named
`Colormap_Visualizer_Zeiss_Script_for_ref.py`; the handoff copy will likely be
renamed to `Colormap_Visualizer.py`. It is the ZEISS-specific entry point and
uses `gom` and NumPy. The important responsibilities are:

- Build and show the user-defined dialog, filter supported inspection
  elements, and synchronize the suggested output filename with the selected
  colormap.
- Recalculate the selected element before reading its data.
- Extract coordinates, normals, optional triangle indices, and scalar values
  from the ZEISS data object.
- Safely handle point-cloud deviation objects: `result_dimension` entries can
  be objects with a `.deviation` field or raw values, and missing values are
  represented as `np.nan`.
- Pass `str(colormap.type)` to the exporter. ZEISS's `ObjectType` wrapper is
  not JSON serializable by itself; a plain string is required.
- Write the exported HTML to the selected path, report errors in the dialog
  log, and attempt to copy the destination folder to the Windows clipboard.
  Clipboard failure is logged separately and does not invalidate a successful
  HTML export.

The helper `generate_html(colormap, out_path)` performs recalculation,
extraction, and export. `parse_deviation(item)` handles point-cloud scalar
objects. `output_path_for(colormap=None)` strips the project extension with
`os.path.splitext`, then appends `_<colormap name>.html` when a selection is
available. This supports project extensions beyond `.zinspect`, including
`.ginspect` and `.gcorrelate`.

The current supported ZEISS element type strings include:

- `surface_comparison_actual_mesh`
- `surface_comparison`
- `inspection_surface_component`
- `inspection_vector_field`

The dialog script is designed to be run inside ZEISS INSPECT, where `gom` is
available. It cannot be executed as a normal standalone Python script without
the ZEISS runtime and dialog resource.

### `library/export_colormap_visualizer.py`

This is the Python API that constructs the standalone HTML. It uses NumPy to
pack data and ZEISS's `gom` and `gom.api.addons` modules to locate the template
resource. Its public signature is:

```python
export_colormap_visualizer(
    coordinate,
    normal,
    scalar_value,
    triangle=None,
    output_filepath=None,
    colormap_type=None,
)
```

Expected arrays are stage-first:

- `coordinate`: `(stages, N, 3)` point/vertex coordinates.
- `normal`: `(stages, N, 3)` normals (mainly used by mesh rendering).
- `scalar_value`: scalar deviation values aligned to points/vertices and
  stages, commonly `(stages, N, 1)`.
- `triangle`: optional triangle indices, commonly `(stages, M, 3)`. `None`, an
  omitted value, or an empty triangle array selects point-cloud rendering.
- `output_filepath`: required destination ending in `.html`.
- `colormap_type`: optional string. Pass `str(colormap.type)` from ZEISS;
  `inspection_vector_field` enables the displacement-vector UI.

For compatibility with point-cloud calls, the function accepts the output
path as the fourth positional argument when triangle data is omitted:

```python
export_colormap_visualizer(coordinates, normals, scalars, output_path)
```

Internally, `_read_template()` calls
`gom.api.addons.get_current_addon()` to identify the active add-on, then
constructs a qualified resource name from that add-on's UUID and the
`scripts/library/standalone_template.html` resource path. The UUID is obtained
dynamically and must not be hard-coded. `gom.Resource` reads the template in
both edit mode (unpacked files) and finalized `.addon` mode (ZIP package),
unlike `Path(__file__)` lookup. The resource is opened, read, and closed in a
`finally` block to release its shared-memory handle; its bytes are decoded as
UTF-8. A missing current add-on or template raises a diagnostic error.

The exporter reads and validates the template before compressing potentially
large arrays. It converts inputs with `np.asarray`, writes arrays to a
compressed in-memory `.npz` using `np.savez_compressed`, and base64-encodes the
archive. It substitutes the embedded archive and type, verifies that each
expected marker appears exactly once, creates destination folders if
necessary, writes generated HTML as a normal output file, and returns the
output path as a string. It does not create temporary `.npz` files. Only the
template is an add-on resource; the exported HTML is written to the
user-selected filesystem path.

### `library/standalone_template.html`

This is the complete browser application: HTML structure, CSS, JavaScript,
rendering runtime, and viewer controls. Its bundled JavaScript includes the 3D
rendering and mesh-picking functionality so generated exports do not request
external libraries or other resources. The ZEISS Python exporter embeds the
data in this file to produce the final one-file artifact.

Important template markers are literal strings and must remain compatible
with the Python exporter:

- `@@EMBEDDED_NPZ_BASE64@@` appears once in the element with id
  `embedded-npz`; the exporter replaces it with the base64-encoded compressed
  NumPy archive.
- `const exportedColormapType="";` appears once; the exporter replaces the
  empty string literal with JSON-encoded `colormap_type`.

These are the actual markers in this codebase. Do not replace them with an
assumed placeholder such as `{{ DATA }}` unless the exporter is changed at the
same time. The UI's important controls include the toolbar, point-size and
vector controls, the viewport canvas, label overlays, legend, status/hint
elements, and stage timeline. The application code after the bundled runtime
contains point-cloud construction, stage navigation, label projection,
vector-overlay, unit-switching, loading, and interaction logic.

The viewer's app-specific JavaScript includes a camera/navigation controller,
a legend controller, and a deviation-label manager. Their implementations
are bundled/minified into the large inline script, so their short internal
symbol names are implementation details and should not be treated as stable
APIs. More useful named extension points include `buildPointData`,
`pointCloudRaycast`, `stageArraysAt`, `threeSigmaRange`, `buildStageData`,
`setStageTimeline`, `projectLabelToStage`, `updateLabelsForStage`,
`buildVectorOverlay`, `setDisplayUnit`, `selectStage`, and the embedded-data
loader.

## 3. Data flow and interoperability

1. **User selects a ZEISS inspection element.** The dialog's element filter
   allows supported comparison, surface-component, and vector-field types.
2. **The ZEISS script recalculates it.**
   `gom.script.sys.recalculate_elements(elements=[colormap])` refreshes the
   inspection result before extraction.
3. **Geometry arrays are read.** Coordinates and normals are converted from
   GOM values using `np.array`. Triangle access is attempted defensively:
   missing, inaccessible, or empty triangle data means the dataset is treated
   as a discrete point cloud.
4. **Scalar values are read.** The script first prefers a usable
   `colormap.data.scalar_value` array, preserving its stage axis. If it is
   absent or unusable, the current fallback converts `colormap.result_dimension`
   entries and reshapes them to `(1, N, 1)`. That fallback is intended for
   single-stage point clouds. If supporting multi-stage point clouds whose
   `scalar_value` is unavailable becomes necessary, the fallback must be
   extended to extract values for every stage instead of reusing this
   single-stage shape.
5. **Exporter resolves its template.** It obtains the current add-on UUID,
   reads `scripts/library/standalone_template.html` through `gom.Resource`,
   and checks both template markers before packaging the arrays.
6. **Exporter packs the data.** The Python function stores `coordinate`,
   `normal`, and `scalar_value`, and includes `triangle` only when non-empty.
   It embeds the compressed archive as base64 and embeds the colormap type.
7. **Browser opens the export offline.** The template decodes and parses the
   embedded NumPy archive in the browser, detects the number of stages from the
   coordinate shape, and constructs either a mesh or point cloud.
8. **Viewer renders and interacts.** The active stage's coordinates and
   scalars are mapped to the 3D view. The legend maps scalar deviations to
   colors. User interaction and view state occur locally in the browser and
   are not sent anywhere.

## 4. Current behavior and feature status

### Rendering and navigation

- Mesh colormaps render as a colored 3D surface; discrete point clouds render
  as colored 3D points.
- The point-cloud view offers Small, Medium, and Large point sizes, and a point
  size change triggers an immediate redraw.
- The navigation controls are: LMB rotate; MMB/RMB pan; mouse wheel zoom;
  Shift+LMB rolls around the view axis.
- Meshes use the ZEISS teal backside color, RGB `(77, 153, 153)`.
- The view includes a reset-zoom control, orientation widget, hover values, and
  deviation labels.

### Legend and scalar values

- Length-valued source scalars are treated as millimeters, regardless of the
  ZEISS project length preference. `gom.app.unit_length` is not passed to the
  exporter. This assumption does not apply to dimensionless values such as
  strain; see the known limitations below.
- The `[mm]` legend unit control switches display between millimeters and
  inches. Values are converted for display (1 inch = 25.4 mm); embedded values
  remain unchanged. The legend limits, shader color thresholds, labels,
  tooltips, and vector colors follow the selected display unit.
- Initial legend scaling uses a three-sigma range. Finite values are gathered
  per visible stage, mean and population standard deviation are calculated,
  and each stage contributes its mean ± 3σ range clipped to that stage's
  observed min/max. The overall initial legend is the union of those ranges.
  Invalid values are ignored. A constant or degenerate range receives a small
  padding so the legend remains usable.
- Upper and lower legend limits initialize unlinked. The user can edit either
  limit, and can later link them. While editing a limit, the mouse wheel
  adjusts the value in 0.001 increments.

### Stages, labels, and vectors

- Multi-stage datasets use the first coordinate axis as the stage axis. Up to
  20 stages display as individual buttons; larger sequences display a
  compressed draggable ruler/timeline. Holding LMB and dragging across the
  timeline requests stages, with redraws queued to keep scrubbing responsive.
- Deviation labels update as the selected stage changes. Surface comparison
  labels are projected to the closest point/surface on subsequent stages,
  since mesh topology or point indices may change. Surface-component and
  vector-field labels use their corresponding point index.
- Only the `inspection_vector_field` type enables vector controls. Vectors
  show stage displacement relative to stage 0 and have show/hide and scaling
  controls. Vector colors are recalculated from their scalar values whenever
  the legend limits or display unit changes. Other multi-stage scalar
  colormaps do not get vector controls.
- Labels are placed with Ctrl+LMB while label mode is active. Esc exits label
  mode. Labels can be dragged, individually deleted, or all cleared.
  **Handoff verification note:** the current template also wires RMB to the
  general pan controller; an explicit RMB-to-exit-label-mode handler was not
  found during this documentation pass. Verify this in the browser and add a
  dedicated handler if right-click completion remains required.

## 5. Constraints and standards

- **Keep exports truly standalone.** Do not introduce CDN scripts, web fonts,
  network requests, adjacent data files, local servers, or installation steps
  for the HTML recipient. Any required browser code must be bundled into the
  template.
- **Keep source/template placeholders in sync.** The exporter currently
  requires exactly one `@@EMBEDDED_NPZ_BASE64@@` marker and one
  `const exportedColormapType="";` marker. Marker counts are validated before
  substitution.
- **Treat the HTML template as an add-on resource.** Its packaged path is
  `scripts/library/standalone_template.html`, matching
  `_TEMPLATE_RESOURCE_PATH` in the exporter. Resolve the current add-on with
  `gom.api.addons.get_current_addon()` and build the qualified resource name
  dynamically with `addon.get_id()`; never hard-code an add-on UUID or use
  `Path(__file__)` to locate this resource. Import `gom` and
  `gom.api.addons` explicitly in the ZEISS runtime. Always close the resource
  handle, including when reading fails.
- **Pass plain strings for ZEISS types.** Always call with
  `colormap_type=str(colormap.type)`. Passing the ZEISS `ObjectType` directly
  previously caused `TypeError: ObjectType is not JSON serializable`.
- **Respect ZEISS data conventions.** Coordinates and length-valued scalar
  values reported from these APIs are in mm in the use case investigated,
  even when the project preference reports another length unit. Display
  conversion belongs in the viewer; do not multiply/reinterpret archived
  source values based on `gom.app.unit_length` without new evidence. Confirm
  whether a scalar represents length or strain before choosing its legend
  unit.
- **Preserve array alignment and stage dimensions.** Coordinates, scalar
  values, normals, and triangles need compatible point and stage indexing.
  Mesh triangles are optional; absence selects point rendering.
- **Keep ZEISS-only behavior out of browser assumptions.** `gom` is available
  only inside INSPECT. The exported page receives arrays and a plain colormap
  type string; it does not access the project or ZEISS APIs.
- **Preserve portable Windows paths.** The example integration script builds
  names with `os.path` and strips the final extension with `os.path.splitext`;
  clipboard copying uses `subprocess.run(['clip'], input=..., text=True,
  check=True)` rather than shell-constructed path strings.
- **Maintain Python compatibility with ZEISS's runtime.** INSPECT bundles its
  own Python, NumPy, and `gom` APIs. Avoid additional dependencies in the
  exporter unless their availability is explicitly verified in the target
  INSPECT version. The exporter now requires ZEISS runtime APIs to resolve the
  packaged template.
- **No runtime input picker in exported pages.** The HTML contains its
  exported dataset; users cannot load or drop another `.npz` into the viewer.

## 6. Known limitations and follow-up work

- **Trend point-cloud scalar fallback:** for discrete point-cloud colormaps,
  `data.scalar_value` may be unavailable, so the ZEISS script currently falls
  back to `result_dimension` and constructs a single-stage `(1, N, 1)` scalar
  array. This supports the current single-stage case, but trend projects with
  multiple point-cloud stages need stage-aware scalar extraction before their
  timeline can show correct deviations at every stage. Do not assume this
  fallback handles multiple stages.
- **Surface-component strain units:** the viewer currently treats scalar
  values as lengths in mm and offers an mm/in display switch. Strain values
  are dimensionless and may be displayed by ZEISS as percent; labeling them
  as mm or converting them to inches is incorrect. The export currently does
  not include scalar-unit metadata. Investigate `colormap.scalar_type` (or the
  corresponding ZEISS API value) and consider passing explicit scalar-unit
  metadata to the exporter so the viewer can preserve `%` and only offer the
  length-unit switch for length-valued colormaps. Verify behavior in ZEISS
  before relying on that property.

## 7. Instructions for the next AI or developer

1. Read this handoff, `README.md`, the exporter, the ZEISS entry script, and
   the relevant section of `standalone_template.html` before changing behavior.
2. Keep changes aligned across the Python exporter, template, README, and
   ZEISS entry script. If a template marker or public function parameter
   changes, update all callers and this document in the same change.
3. Preserve the public import and call style unless there is a clear migration
   plan. The intended ZEISS caller is `from library import
   export_colormap_visualizer`.
4. Make changes with real ZEISS constraints in mind. This environment may not
   have `gom` or the INSPECT application, so distinguish code-level inspection
   from actual in-application verification. Do not claim ZEISS validation
   unless it was performed in INSPECT.
5. For viewer changes, preserve offline operation and test both meshes and
   point clouds, single and multiple stages, and relevant colormap types when
   suitable inputs are available. Verify point-size changes, stage scrubbing,
   label values/colors, editable legend limits, unit conversion, and the
   vector-only UI gate when those areas are affected.
6. When investigating export failures, check the actual shapes, dtypes,
   triangle availability, scalar source, stage count, and `str(colormap.type)`
   at the ZEISS boundary. Do not infer shape or units from the project
   preference alone.
7. Keep the known limitations above visible when extending the feature set.
   In particular, don't silently present single-stage fallback values as
   trend data, or label strain values as a length unit.
8. Resolve the label-mode right-click behavior noted above against the user's
   desired interaction before changing pointer events; RMB is also the pan
   gesture, so event ordering and label mode need consideration.
9. Keep comments useful for debugging GOM-specific behavior and parsing
   boundaries, but avoid adding comments that merely restate every line.
10. Regenerate the HTML from the exporter after template changes when an
   integration/visual review artifact is needed. Generated HTML is a snapshot
   and must be regenerated to include source/template updates.
11. Do not reintroduce a button into the existing viewer app or `.npz` loading
   into the exported page unless the user explicitly changes the scope. The
   current requested workflow is to call the exporter from a ZEISS INSPECT
   script/button and share the resulting HTML.

## 8. Useful canonical examples

### Mesh export

```python
export_colormap_visualizer(
    coordinates,
    normals,
    scalar_values,
    triangles,
    output_path,
    colormap_type=str(colormap.type),
)
```

### Point-cloud export

```python
export_colormap_visualizer(
    coordinates,
    normals,
    scalar_values,
    None,
    output_path,
    colormap_type=str(colormap.type),
)
```

Alternatively, when triangles are omitted, pass `output_path` as the fourth
positional argument. Use `None` only for genuinely absent triangle data; an
empty triangle array is also treated as point data.

