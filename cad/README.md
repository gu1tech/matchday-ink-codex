# Curated enclosure files

This folder contains one selected enclosure set, not all development iterations.

- `stl/front.stl`, `body.stl`, `rear.stl`: selected final shell parts.
- `stl/esp32-carrier.stl`: existing carrier; use with the alignment repair below.
- `stl/two-glue-feet.stl`: two independent mounting feet for actual USB alignment.
- `print-projects/`: corresponding Bambu Studio projects. Import one intended job at a time; do not print STL duplicates as well.

Historical v11/v13 names are retained in Bambu project filenames to preserve provenance. They do not indicate multiple alternative final bodies.

Body starting profile: A1, 0.4 mm nozzle, PLA Matte, 0.16 mm layers, 3 walls, 15% infill; front mating rim down, build-plate-only supports, 45° threshold, 4 mm brim. Review the project orientation and supports in your slicer before printing. These settings are not universal material tolerances.

Repair feet: 10 × 8 × 4 mm each, 1.6 mm blind pilot hole. Print 0.20 mm, 4 walls, 100% infill, no supports. Use two M2×4 mm screws through the plastic carrier tabs. Align the USB socket first and glue the feet in their actual required positions. If old posts interfere, flatten only the obstructing posts; do not change cover height. See the hardware guide.

These are exported manufacturing artifacts. A clean, fully parametric CAD regeneration pipeline is not included in this release. The owner accepted the assembled enclosure with the mounting repair; another printer/board still requires a dry fit.
