# Working rules

## Board viewer

The user checks the board in the viewer artifact https://claude.ai/artifact/1WNC9PWKXeD4q3HKXAcR2r (schematic sheets, PCB placement, interactive 3D).

After committing a change to `hw/kicad/` or `hw/lib/`:

1. Run `hw/view/build.sh --if-changed` (about 1 minute; exit 3 means the design inputs did not change, so stop here).
2. Republish to the same URL with the Artifact tool:
   - `url`: the URL above
   - `file_path`: `hw/view/build/index.html`
   - `root`: `hw/view/build`
   - `files`: every file under `hw/view/build/` except `index.html` and `stamp.txt`
   - `label`: the short commit hash from `hw/view/build/meta.json`
3. Tell the user that the viewer was updated, and give the commit.

Open pages pick up the new version by themselves and keep their tab, sheet and camera.
Design-specific text (commit, counts, parts without 3D models, sheet list) comes from `build/meta.json`, so do not hard-code it into `hw/view/index.html`.
