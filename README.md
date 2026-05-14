# SboxSource1import v1.0.0

Batch import Source 1 engine assets into Source 2 / s&box format.  
GUI + CLI. Python. Inspired by Valve's internal tools.

Based on [source2utils](https://github.com/AlpyneDreams/source2utils).

---

## Quick Start

1. [Download](https://github.com/kristiker/source1import/releases)
2. `pip install -r requirements.txt`
3. Double-click `source1import.pyw` to launch the GUI

---

## How to Use (GUI Walkthrough)

### 1. Launch the tool

```
双击 source1import.pyw
```

You'll see the GUI window titled **"SboxSource1import v1.0.0"**.

### 2. Set Import Path

Click the **`…`** button next to **Import Game**. Navigate to the folder containing your Source 1 assets — this must be a game/mod root with `gameinfo.txt` inside it.

For VJBase / GMod content, point to the unpacked addon folder:
```
F:\DevProject\Sbox\gmod解包\test
```
(The tool will auto-detect `gameinfo.txt` and parse the game name.)

### 3. Set Export Path

Click the **`…`** button next to **Export Game**. Navigate to your s&box project or addon root:

For s&box:
```
F:\DevProject\Sbox\testzombie
```
Make sure the dropdown on the right is set to **`sbox`**.

### 4. Choose What to Import

The row of checkboxes below the path inputs controls which asset types get imported:

| Checkbox | What it does |
|----------|-------------|
| **Import All** | Toggle everything on/off at once |
| **Overwrite All** | Overwrite existing files rather than skip |

Below that, each tab corresponds to one asset type. Click a tab name to see its options.

### 5. Configure Models Tab (QC Import)

This is the most important tab for VJBase. Click the **Models** tab and set:

```
☑ Generate VMDL models
  ☑ Overwrite Existing VMDLs
  ☐ Generate from MDL files          ← UNCHECK
  ☐ Search for files in Source 1 dir
  ☐ Temporary s&box path fix
  ☑ Import from QC (experimental)    ← CHECK THIS
```

> **Important**: Uncheck **"Generate from MDL files"** and check **"Import from QC (experimental)"**. This tells the tool to read `.qc` files and generate full ModelDoc VMDLs (with animations, bodygroups, LODs, attachments) instead of simple MDL wrappers.

### 6. Configure Other Tabs

| Tab | Recommended Settings |
|-----|---------------------|
| **Textures** | ☑ Decompile VTF to sources. Multithreaded ON. |
| **Materials** | ☑ Import VMT materials. Simple shader where possible ON. |
| **Sounds** | ☑ Import Sound files. Overwrite as needed. |

### 7. Run

Click **Go**. The console at the bottom will show progress:
```
Source 2 VMDL Generator!
 - Generating VMDL from QC!
  [bodygroup] Assigned 12 LOD meshes to bodygroups
+ Saved models/vj_zombies/slow_main.vmdl
Looks like we are done!
```

### 8. Result

Check your s&box project's `Assets/` folder:
```
Assets/
├─ materials/   ← VMAT materials
├─ models/      ← VMDL models
├─ sounds/      ← imported audio + .sound assets
└─ particles/   ← particle systems
```

---

## GUI Feature Tabs

| Tab | Function | Options |
|-----|----------|---------|
| **Textures** | VTF → TGA decompile | Overwrite, ignore cubemaps, multithreaded, thread count |
| **Materials** | VMT → VMAT import | Overwrite VMATs / modified, simple shader fallback, normal invert, proxy ignore |
| **Models** | MDL/QC → VMDL generation | Overwrite, from MDL, from QC (experimental), copy src1 dir, s&box path fix |
| **Particles** | PCF → s&box particle system | Overwrite, behavior version |
| **Maps** | VMF/BSP → VMap | Overwrite, VMF entities, BSP entities |
| **Scenes** | VCD → vcdlist | Everything to root |
| **Scripts** | Soundscapes / GameSounds / Surfaces / Misc | Overwrite |
| **Sessions** | SFM session import | Overwrite |
| **Sounds** | WAV/MP3/OGG → s&box sounds | Overwrite, auto-generate `.sound` asset files |

---

## Model Import (QC → VMDL)

The model importer reads `.qc` files and generates ModelDoc VMDL. Below is every QC directive it handles.

### Meshes & Bodygroups

| QC Directive | Output |
|-------------|--------|
| `$bodygroup "name" { ... }` | `BodyGroupList` → `BodyGroup` → `BodyGroupChoice` |
| `$bodygroup ".../blank"` | Empty bodygroup choice (headcrab off, etc.) |
| `$body "name" "file.smd"` | `RenderMeshFile` (single mesh) |
| `$model "name" "file.smd"` | `RenderMeshFile` (single mesh) |
| `$lod N { replacemodel ... }` | `LODGroup` with `switch_threshold` and mesh arrays |
| `$lod / replacebone` | Bone replacement at LOD level |
| `$lod / nofacial` | Facial animation disable at LOD level |

> **VJBase fix**: Single-choice bodygroups (e.g. `$bodygroup "studio"`) are preserved so LOD variant meshes can be correctly auto-assigned to the same bodygroup. This eliminates the `"not in any bodygroups"` compiler warning and ensures proper visibility of LOD meshes when bodygroup choices change.

### Animations

| QC Directive | Output |
|-------------|--------|
| `$animation "name" file.smd { options }` | `AnimFile` node (single animation) |
| `$sequence "name" { file1 file2 ... blend name min max ... }` | `AnimFile` or `1DBlend` node (dynamic blend) |
| `$poseparameter "name" min max` | `PoseParam` |
| `$declaresequence "name"` | Sequence declaration → prefab |
| `$weightlist / $defaultweightlist` | `WeightList` (bone weight sets) |

**Animation options supported**: `fps`, `loop`, `hidden`, `delta`, `worldspace`, `fadein`, `fadeout`, `activity` / `ACT_*`, `reverse`, `weightlist`, `frame`, `blend`, `blendlayer`, `poseparameter`, `posecycle`, `snap`, `realtime`, `compress`, `autoplay`, `addlayer`, `motion extract axis`, `node`, `transition`, `keyvalues`

**Sequence blend options**: `blend name min max`, `blendwidth`, `blendref`, `calcblend`, `blendcenter`

### Animation Events (`{ event ... }`)

| QC Event | Output |
|----------|--------|
| `{ event AE_CL_PLAYSOUND frame "sound" }` | `AnimEvent` with `event_class="AE_CL_PLAYSOUND"`, `event_keys.name="sound"` |
| `{ event AE_SV_PLAYSOUND frame "sound" }` | Server-side sound event |
| `{ event AE_CL_STOPSOUND frame "sound" }` | Stop sound event |
| `{ event 1100 frame "custom" }` | Generic event (via AE_IDS mapping: `1100 → AE_CL_PLAYSOUND`) |
| `{ event 6006/6007 frame "..." }` | Footstep events |

> **TODO**: When a sound table (HL2 `game_sounds_*.txt` or VJBase `sounds.lua`) is loaded, Source 1 logical sound names like `"Zombie.Pain"` will be auto-resolved to actual WAV paths in the `.vmdl`. Currently, unresolved names are forwarded to C# runtime code for handling via the NPC's `SoundTbl_*` tables.

### Collision & Physics

| QC Directive | Output |
|-------------|--------|
| `$collisionmodel "file.smd"` | `PhysicsHullFile` |
| `$collisionjoints "file.smd"` | `PhysicsHullFile` |
| `$bbox minx miny minz maxx maxy maxz` | `Bounds_Hull` |
| `$cbox minx miny minz maxx maxy maxz` | `Bounds_View` |
| `$surfaceprop "name"` | Global surface property |
| `$origin x y z` | Model origin offset |

### Materials & Textures

| QC Directive | Output |
|-------------|--------|
| `$cdmaterials "path/"` | `DefaultMaterialGroup` — auto-maps VMT names to VMAT files |
| `$texturegroup` | `MaterialGroup` (skin variants with remap chains) |
| `$renamematerial "old" "new"` | Material remap update |

The material path resolver:
- Scans `content/materials/` for `.vmat` files
- Matches by stem name (case-insensitive)
- Falls back to expected path with warning if no match found
- Logs all remaps and misses to `_qc_import.log`

### Skeleton, Attachments & Misc

| QC Directive | Output |
|-------------|--------|
| `$definebone "name" "parent" px py pz rx ry rz` | `Bone` → `Skeleton` |
| `$attachment "name" "bone" x y z` | `Attachment` |
| `$staticprop` | `model_archetype="static_prop_model"` |
| `$includemodel "path"` | Base model reference |
| `$include "file.qci"` | Prefab include |
| `$pushd "dir"` / `$popd` | Directory stack |
| `$keyvalues { prop_data ... }` | `GenericGameData` |
| `$hierarchy` | Bone hierarchy (parsed, not generated) |

### Deliberately Skipped

| QC Feature | Why |
|-----------|-----|
| `ikrule` (IK ground clamping) | Source 2 uses AnimGraph Procedural Bone nodes instead |
| `jigglebone` | s&box has no jiggle bone system |
| `bonemerge` | Not needed for VJBase (headcrabs use bodygroups) |
| `walkframe` | Source 2 uses AnimGraph BlendSpaces |

---

## Sound Import

The **Sounds** tab copies audio files from Source 1 `sound/` → s&box `sounds/` and automatically generates `.sound` asset files.

- Supported formats: `.wav`, `.mp3`, `.ogg`
- Preserves directory structure
- Each audio file gets a `.sound` asset with default parameters (volume 1.0, distance max 3000)
- `Overwrite` toggle controls whether existing files are replaced

---

## CLI Usage

```bash
cd utils
python models_import.py    -i "C:/.../source1game" -e "D:/.../sbox/addons/myaddon" -b sbox
python materials_import.py -i "C:/.../source1game" -e "D:/.../sbox/addons/myaddon" -b sbox "materials/skybox"
python particles_import.py -i "C:/.../source1game" -e "D:/.../sbox/addons/myaddon"
python sound_import.py     -i "C:/.../source1game" -e "D:/.../sbox/addons/myaddon" -b sbox
python scenes_import.py    -i "C:/.../source1game" -e hlvr_addons/myaddon
python scripts_import.py   -i "C:/.../source1game" -e "D:/.../sbox/addons/myaddon" -b sbox
```

**Flags**:
- `-i <dir>` — Source 1 game root (must contain `gameinfo.txt`)
- `-e <dir/mod>` — Source 2 / s&box addon path
- `-b <branch>` — Target branch: `hlvr` (default), `sbox`, `cs2`, `dota2`, `steamvr`, `adj`
- `[filter]` — optional path filter at end

---

## VJBase-Specific Notes

This fork includes fixes for the [VJ-Base-S-box](https://github.com/qq781217732/VJ-Base-S-box) project:

1. **Single-choice bodygroups preserved** — `$bodygroup "studio"` no longer flattened; mesh name retains SMD association
2. **LOD meshes auto-assigned to bodygroups** — `_lod{N}` variants inherit their base mesh's bodygroup choice
3. **Animation event bridge** (C# side) — `SkinnedModelRenderer` callbacks → `BaseNPC.OnAnimEvent()` virtual method
4. **Sound import** — New Sounds tab with WAV/MP3 → `.sound` asset generation

---

## Requirements

- Python ≥ 3.10
- `pip install -r requirements.txt`
- Source 1 game directory with `gameinfo.txt`

## Notes

- Move the entire Source 1 `models` folder to `content/` before importing models
- Move the entire Source 1 `sound` folder to `content/` and rename to `sounds` — or use the Sounds import tab
- Materials won't make use of the PBR renderer; tweak them manually or use [css2-inf-materials](https://github.com/kristiker/css2-inf-materials)
- Map import: read the [Valve guide](https://developer.valvesoftware.com/wiki/Half-Life:_Alyx_Workshop_Tools/Importing_Source_1_Maps)
- CS2: Valve will likely ship an official source1import with workshop tools
