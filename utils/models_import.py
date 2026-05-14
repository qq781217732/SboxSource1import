import itertools
import shutil
from typing import Literal, Type, Union
import shared.base_utils2 as sh
from pathlib import Path
from itertools import tee
from srctools import smd
from shared.keyvalues3 import KV3File, KV3Header

"""
Import Source Engine models to Source 2

* Generates simple VMDL files linking the MDL.
    * This method has the highest compatibility and is fastest.
    * The model won't be editable until its decompiled from vmdl_c via ModelDoc.
    * Some complex models might crash the compiler i.e. L4D characters and cs animstates.
    * Some less important parameters like $keyvalues are ignored with current compilers.
    * The format for `models/example.vmdl` is:
        <!-- kv3 encoding:text:version{e21c7f3c-8a33-41c5-9977-a76d3a32aa0d} format:generic:version{7412167c-06e9-4698-aff2-e63eb59037e7} -->
        {
            m_sMDLFilename = "models/example.mdl"
        }

* Generates (poorly) translated VMDL files based on QC.
    * This method is less stable. The VMDL files are in ModelDoc format.
    * Instead of decompiling, original fbx/dmx/smd files are used.
"""

# mdl import
IMPORT_MDL = True

# qc import
IMPORT_QC = False
IGNORE_SINGLEBODY_BODYGROUPS = True
IGNORE_BBOX = False

SHOULD_OVERWRITE = False
SAMPBOX = False
COPY_FROM_SRC1_DIR = False

models = Path('models')
modelsrc = Path('modelsrc')

def main():
    print('Source 2 VMDL Generator!')
    _IMPORT_LOG_MESSAGES.clear()
    
    if IMPORT_MDL:
        if COPY_FROM_SRC1_DIR:
            print(' - Copying MDL files from src1 dir!')
            for s1_model_resource in itertools.chain(
                sh.src(models).rglob('*.mdl'),
                sh.src(models).rglob('*.phy'),
                sh.src(models).rglob('*.vvd'),
                sh.src(models).rglob('*.dx90.vtx'),
            ):
                output_path = sh.output(s1_model_resource)
                output_path.parent.MakeDir()
                shutil.copy(s1_model_resource, output_path)

        print('- Generating VMDL from MDL!')
        mdl_files = sh.collect(models, '.mdl', '.vmdl', SHOULD_OVERWRITE, searchPath=sh.output(models))

        for mdl in mdl_files:
            ImportMDLtoVMDL(mdl)

    if IMPORT_QC:
        if COPY_FROM_SRC1_DIR:
            print(' - Copying model sources from src1 dir!')
            for s1_model_resource in itertools.chain(
                sh.src(modelsrc).rglob('*.qc'),
                sh.src(modelsrc).rglob('*.qci'),
                sh.src(modelsrc).rglob('*.smd'),
                sh.src(modelsrc).rglob('*.dmx'),
                sh.src(modelsrc).rglob('*.fbx'),
                sh.src(modelsrc).rglob('*.vta'),
            ):
                output_path = sh.output(models/s1_model_resource.local.relative_to(modelsrc))
                output_path.parent.MakeDir()
                shutil.copyfile(s1_model_resource, output_path)
                sh.status(f"Copied {s1_model_resource.local}")

        print('- Generating VMDL from QC!')
        qci_files = sh.collect(models, '.qci', '.vmdl', True, searchPath=sh.output(models))
        qc_files = sh.collect(models, '.qc', '.vmdl', True, searchPath=sh.output(models))
        
        for qci in qci_files:
            ImportQCtoVMDL(qci)

        for qc in qc_files:
            ImportQCtoVMDL(qc)

        _write_log()

    print("Looks like we are done!")


def ImportMDLtoVMDL(mdl_path: Path):
    vmdl_path = mdl_path.with_suffix('.vmdl')
    vmdl = KV3File(
        m_sMDLFilename = ("../"*SAMPBOX) + mdl_path.local.as_posix()
    )
    vmdl_path.write_text(vmdl.ToString())
    print('+ Generated', vmdl_path.local)
    return vmdl_path

from shared.qc import QC, QCBuilder, QCParseError
from shared.modeldoc import ModelDoc, _BaseNode, _Node

DEFAULT_WEIGHTLIST_NAME = "_qc_default"

# --- import log ---
_IMPORT_LOG_PATH: Path = None
_IMPORT_LOG_MESSAGES: list[str] = []

def _log(msg: str):
    """Print to stdout and buffer for later writing to log file."""
    print(msg)
    _IMPORT_LOG_MESSAGES.append(msg)

def _write_log():
    """Flush buffered messages to log file in the tool directory."""
    global _IMPORT_LOG_PATH
    if _IMPORT_LOG_PATH is None:
        _IMPORT_LOG_PATH = Path(__file__).resolve().parent / '_qc_import.log'
    content = '\n'.join(_IMPORT_LOG_MESSAGES)
    if not content:
        content = '# No material warnings or remaps.'
    _IMPORT_LOG_PATH.write_text(content, encoding='utf-8')
    print(f'\nQC import log → {_IMPORT_LOG_PATH}')

# --- material path index (lazy-built, shared across QC imports) ---
_VMAT_INDEX: dict[str, str] = {}

def _build_vmat_index():
    """Scan EXPORT_CONTENT/materials for all .vmat files, keyed by normalised path (with .vmat)."""
    _VMAT_INDEX.clear()
    mats_root = sh.EXPORT_CONTENT / 'materials'
    if not mats_root.is_dir():
        return
    for vmat in mats_root.rglob('*.vmat'):
        key = vmat.relative_to(sh.EXPORT_CONTENT).as_posix().lower()
        val = vmat.relative_to(sh.EXPORT_CONTENT).as_posix()
        _VMAT_INDEX[key] = val

AE_IDS = {
    -1: 'AE_INVALID',
    5004: 'AE_CL_PLAYSOUND',
    7777: 'AE_SV_PLAYSOUND',
    7777: 'AE_CL_STOPSOUND',
    6001: 'CL_EVENT_EJECTBRASS1',
    3014: 'EVENT_WEAPON_PISTOL_FIRE',
}


def ImportQCtoVMDL(qc_path: Path):
    vmdl = ModelDocVMDL()
    
    # local paths
    active_folder: Path = qc_path.local.parent
    dir_stack: list[Path] = []
    
    def fixup_filepath(path):
        # resolve it on a full path so that it doesn't resolve to CWD
        resolved = (sh.EXPORT_CONTENT / active_folder / path).resolve()
        if resolved.is_file():
            return resolved.local.as_posix()
        # try scanning subdirectories for the same filename (case-insensitive)
        name = Path(path).name.lower()
        parent_dir = (sh.EXPORT_CONTENT / active_folder).resolve()
        for candidate in parent_dir.rglob(name):
            return candidate.local.as_posix()
        # fall back to the original path even if it doesn't exist
        return resolved.local.as_posix()

    def fixup_material_path(name_or_path: str, is_path: bool = False):
        if not is_path:
            expected = (Path("materials/" + cdmaterials) / name_or_path ).as_posix()
        else:
            expected = (sh.EXPORT_CONTENT / Path("materials/" + cdmaterials) / name_or_path ).resolve().local.as_posix()

        # --- verify .vmat actually exists; case-insensitive fallback ---
        vmat_key = (expected + '.vmat').lower()
        if vmat_key not in _VMAT_INDEX:
            if not _VMAT_INDEX:
                _build_vmat_index()
        if vmat_key in _VMAT_INDEX:
            return _VMAT_INDEX[vmat_key]

        # case-insensitive stem match (e.g. Fast05 → fast05)
        exp_stem = Path(expected).stem.lower()
        candidates = {k: v for k, v in _VMAT_INDEX.items() if Path(k).stem == exp_stem}
        if len(candidates) == 1:
            return next(iter(candidates.values()))

        # no reliable match — warn and keep expected path
        _log(f"  [material] MISS: '{name_or_path}' → no .vmat found (expected: {expected})")
        return expected + '.vmat'

    material_names: set[str] = set()
    cdmaterials = "" # TODO: support multiple cdmaterials

    def add_rendermesh(name: str, reference_mesh_file: str):
        body = QC.body()
        body.name = name
        body.mesh_filename = reference_mesh_file
        return add_rendermesh_from_body(body)
        
    def add_rendermesh_from_body(body: QC.body):
        rendermesh_file = sh.EXPORT_CONTENT / fixup_filepath(body.mesh_filename)
        if rendermesh_file.is_file():
            if rendermesh_file.suffix == ".smd":
                with open(rendermesh_file, "rb") as fp:
                    ref = smd.Mesh.parse_smd(fp)
                    for tri in ref.triangles:
                        material_names.add(tri.mat)
            elif rendermesh_file.suffix == ".dmx":
                #import shared.datamodel as dmx
                #dmx.load(rendermesh_file)
                ...

        else:
            sh.status(f"missing-mesh {rendermesh_file}")
        rendermeshfile = ModelDoc.RenderMeshFile(
            name = body.name,
            filename = rendermesh_file.local.as_posix(),
            import_scale = body.scale,
        )
        return vmdl.add_to_appropriate_list(rendermeshfile)

    with qc_path.open() as fp:
        try:
            qc_commands: list["QC.command" | str] = QCBuilder().parse(fp.read())
        except Exception:
            print("Failed to parse QC file", qc_path)
            raise

    model_name = ""
    global_surfaceprop = "default"
    origin = (0, 0, 0)
    sequences_declared: list[str] = []
    lod0 = None
    skeleton = ModelDoc.Skeleton()
    bHasDefaultWeightlist = False

    bone_name_fixup = lambda name: name.replace('.', '_')

    # --- first pass: collect $animation definitions ---
    animation_defs: dict[str, QC.animation] = {}
    pose_parameter_defs: dict[str, QC.poseparameter] = {}
    for command in qc_commands:
        if isinstance(command, QC.animation):
            animation_defs[command.name] = command
        elif isinstance(command, QC.poseparameter):
            pose_parameter_defs[command.name] = command
            _log(f"  [poseparam] '{command.name}': range=[{command.min}, {command.max}], wrap={command.wrap}")
            p = ModelDoc.PoseParam(
                name=command.name,
                poseparam_min=command.min,
                poseparam_max=command.max,
                poseparam_looping=command.wrap > 0,
                poseparam_loop=command.wrap if command.wrap > 0 else 0.0,
            )
            vmdl.add_to_appropriate_list(p)

    # These first
    for command in qc_commands:
        if isinstance(command, QC.surfaceprop):
            global_surfaceprop = command.name
        elif isinstance(command, QC.origin):
            origin = command.x, command.y, command.z

    for command in qc_commands:
        match command:
            case QC.staticprop():
                vmdl.root.model_archetype = "static_prop_model"
                vmdl.root.primary_associated_entity = "prop_static"
            case QC.popd():
                try:
                    active_folder = dir_stack.pop()
                except IndexError:
                    pass
            case QC.pushd():
                dir_stack.append(active_folder)
                active_folder = active_folder / command.path
        
        if isinstance(command, QC.include):
            prefab_path = (active_folder / command.filename).with_suffix('.vmdl_prefab')
            prefab = ModelDoc.Prefab(target_file=prefab_path.as_posix())
            vmdl.add_to_appropriate_list(prefab)

        elif isinstance(command, QC.modelname):
            model_name = command.filename

        # https://developer.valvesoftware.com/wiki/$body
        elif isinstance(command, QC.body):
            command: QC.body
            add_rendermesh_from_body(command)

        # https://developer.valvesoftware.com/wiki/$model_(QC)
        elif isinstance(command, QC.model):
            command: QC.model
            add_rendermesh(command.name, command.mesh_filename)
            ... # Options

        # https://developer.valvesoftware.com/wiki/$animation
        elif isinstance(command, QC.animation):
            command: QC.animation
            src = fixup_filepath(command.mesh_filename)
            animfile = ModelDoc.AnimFile(name=command.name)
            animfile.source_filename = src
            if bHasDefaultWeightlist:
                animfile.weight_list_name = DEFAULT_WEIGHTLIST_NAME

            optionsiter = iter(command.options) if command.options else iter([])
            while option := next(optionsiter, False):
                if isinstance(option, list):
                    continue
                option = option.lower()
                if option == 'loop':
                    animfile.looping = True
                elif option == 'fps':
                    animfile.framerate = next(optionsiter)
                elif option == 'hidden':
                    animfile.hidden = True
                elif option == 'delta':
                    animfile.delta = True
                elif option == 'worldspace':
                    animfile.worldSpace = True
                elif option == 'fadein':
                    animfile.fade_in_time = next(optionsiter)
                elif option == 'fadeout':
                    animfile.fade_out_time = next(optionsiter)
                elif option == 'weightlist':
                    animfile.weight_list_name = next(optionsiter)
                elif option == 'reverse':
                    animfile.reverse = True
                elif option == 'activity' or option.startswith('act_'):
                    if option.startswith('act_'):
                        animfile.activity_name = option.upper()
                    else:
                        animfile.activity_name = str(next(optionsiter)).upper()
                    animfile.activity_weight = next(optionsiter)

            vmdl.add_to_appropriate_list(animfile)

        # https://developer.valvesoftware.com/wiki/$sequence
        elif isinstance(command, QC.sequence):
            command: QC.sequence
            # --- split options list into filenames + keywords ---
            ANIM_KEYWORDS = {
                'activity', 'act_', 'fadein', 'fadeout', 'fps', 'loop', 'snap',
                'frame', 'reverse', 'hidden', 'delta', 'predelta', 'walkframe',
                'addlayer', 'blendlayer', 'blend', 'origin', 'angles', 'rotate',
                'scale', 'motion extract axis', 'autoplay', 'posecycle',
                'poseparameter', 'node', 'ikrule', 'realtime', 'worldspace',
                'weightlist', 'localhierarchy', 'compress',
            }
            def _looks_like_filename(token) -> bool:
                if not isinstance(token, str):
                    return False
                if token.endswith('.smd') or token.endswith('.dmx'):
                    return True
                if '/' in token or '\\' in token:
                    return True
                tl = token.lower()
                for kw in ANIM_KEYWORDS:
                    if tl == kw or tl.startswith(kw):
                        return False
                try:
                    float(token)
                    return False
                except ValueError:
                    pass
                return True

            # Separate filename token(s) from option keywords
            file_tokens = []
            for t in command.options:
                if _looks_like_filename(t):
                    file_tokens.append(t)
                else:
                    break
            if not file_tokens:
                file_tokens = [command.options[0]]

            # Resolve each file_token: may be $animation ref or direct filename
            resolved_srcs = []
            for ft in file_tokens:
                if ft in animation_defs:
                    src = fixup_filepath(animation_defs[ft].mesh_filename)
                else:
                    src = ft
                    if not (src.endswith('.smd') or src.endswith('.dmx')):
                        src += '.smd'
                    src = fixup_filepath(src)
                resolved_srcs.append(src)

            rest_opts = command.options[len(file_tokens):]

            # Scan remaining options for blend parameters
            blend_name = None
            blend_min = blend_max = 0.0
            rest_list = list(rest_opts)  # need multiple passes
            i = 0
            while i < len(rest_list):
                opt = rest_list[i]
                if isinstance(opt, str) and opt.lower() == 'blend':
                    if i + 2 < len(rest_list):
                        blend_name = rest_list[i + 1]
                        blend_min = float(rest_list[i + 2])
                        blend_max = float(rest_list[i + 3])
                        i += 4
                        continue
                i += 1

            if len(file_tokens) > 1 and blend_name is not None:
                # === Create 1DBlend for waypoint-blend sequence ===
                blend1d = ModelDoc.Blend1D(name=command.name)
                blend1d.weight_list_name = blend_name
                blend1d.poseParam = blend_name

                # Calculate evenly spaced blend weights across the range
                n = len(file_tokens)
                step = (blend_max - blend_min) / (n - 1)
                for idx, (ft, src) in enumerate(zip(file_tokens, resolved_srcs)):
                    weight = blend_min + idx * step
                    blend1d.blendList.append({"name": ft, "weight": weight})

                if bHasDefaultWeightlist:
                    blend1d.weight_list_name = blend_name or DEFAULT_WEIGHTLIST_NAME

                # Parse remaining options (activity, events, fadein, etc.) onto blend1d
                optionsiter = iter(rest_list)
                while option := next(optionsiter, False):
                    if isinstance(option, list):
                        if option[0].lower() != 'event':
                            continue
                        event_class: str = option[1]
                        if str.isdigit(event_class):
                            try:
                                event_class = AE_IDS[int(event_class)]
                            except KeyError:
                                print("Unknown AnimEvent ID", event_class)
                        animevent = ModelDoc.AnimFile.AnimEvent(
                            event_class=event_class,
                            event_frame=option[2],
                            note=" ".join(option[3:]),
                        )
                        if event_class in ('AE_CL_PLAYSOUND', 'AE_SV_PLAYSOUND', 'AE_CL_STOPSOUND'):
                            animevent.event_keys["name"] = option[3]
                        blend1d.children.append(animevent)
                        continue

                    option = option.lower()

                    if option == 'loop':
                        blend1d.looping = True
                    elif option == 'hidden':
                        blend1d.hidden = True
                    elif option == 'fps':
                        next(optionsiter)  # skip for 1DBlend
                    elif option == 'activity' or option.startswith('act_'):
                        if option.startswith('act_'):
                            blend1d.activity_name = option.upper()
                        else:
                            blend1d.activity_name = str(next(optionsiter)).upper()
                        blend1d.activity_weight = next(optionsiter)
                    elif option == 'fadein':
                        blend1d.fade_in_time = next(optionsiter)
                    elif option == 'fadeout':
                        blend1d.fade_out_time = next(optionsiter)
                    elif option == 'weightlist':
                        blend1d.weight_list_name = next(optionsiter)
                    elif option == 'delta':
                        blend1d.delta = True
                    elif option == 'worldspace':
                        blend1d.worldSpace = True
                    elif option == 'blend':
                        # already consumed above, skip 3 more tokens
                        next(optionsiter); next(optionsiter); next(optionsiter)
                    elif option == 'blendwidth':
                        next(optionsiter)  # skip

                vmdl.add_to_appropriate_list(blend1d)
                _log(f"  [sequence] '{command.name}': 1DBlend with {n} waypoints, param='{blend_name}', range=[{blend_min}, {blend_max}]")

            else:
                # === Single-file sequence: regular AnimFile ===
                src = resolved_srcs[0]

                animfile = ModelDoc.AnimFile(name=command.name)
                animfile.source_filename = src
                animfiles = [animfile]

                if bHasDefaultWeightlist:
                    animfile.weight_list_name = DEFAULT_WEIGHTLIST_NAME

                optionsiter = iter(rest_list)

                while option := next(optionsiter, False):
                    # Handle subgroups first
                    if isinstance(option, list):
                        if option[0].lower() != 'event':
                            continue
                        event_class: str = option[1]
                        if str.isdigit(event_class):
                            try:
                                event_class = AE_IDS[int(event_class)]
                            except KeyError:
                                print("Unknown AnimEvent ID", event_class)
                        animevent = animfile.AnimEvent(
                            event_class=event_class,
                            event_frame=option[2],
                            note=" ".join(option[3:]),
                        )
                        if event_class in ('AE_CL_PLAYSOUND', 'AE_SV_PLAYSOUND', 'AE_CL_STOPSOUND'):
                            animevent.event_keys["name"] = option[3]
                        elif event_class == 'whatever':
                            ...

                        animfile.children.append(animevent)
                        continue

                    option = option.lower()

                    if option == 'frame':
                        animfile.start_frame, animfile.end_frame = next(optionsiter), next(optionsiter)
                    elif option in ('origin', 'angles'):
                        x,y,z = next(optionsiter), next(optionsiter), next(optionsiter)
                    elif option in ('rotate', 'scale'):
                        f = next(optionsiter)
                    elif option == 'reverse': animfile.reverse = True
                    elif option == 'loop': animfile.looping = True
                    elif option == 'hidden': animfile.hidden = True
                    elif option == 'fps': animfile.framerate = next(optionsiter)
                    elif option == 'motion extract axis': ...
                    elif option == 'activity' or option.startswith('act_'):
                        if option.startswith('act_'):
                            animfile.activity_name = option.upper()
                        else:
                            animfile.activity_name = str(next(optionsiter)).upper()
                        animfile.activity_weight = next(optionsiter)
                    elif option == 'autoplay': ...
                    elif option == 'addlayer':
                        sequence = next(optionsiter)
                    elif option == 'blendlayer':
                        sequence = next(optionsiter)
                        startframe, peakframe, tailframe, endframe = next(optionsiter), next(optionsiter), next(optionsiter), next(optionsiter)
                        optionsiter, blendlayer_options = tee(optionsiter)
                        while option:=next(blendlayer_options, False):
                            if option == 'spline': ...
                            elif option == 'xfade': ...
                            elif option == 'poseparameter':
                                poseparameter_name: str = next(blendlayer_options)
                                animfile.poseParam = poseparameter_name
                            elif option == 'noblend': ...
                            elif option == 'local': ...
                            else:
                                optionsiter = blendlayer_options
                                break
                    elif option == 'worldspace': animfile.worldSpace = True
                    elif option == 'snap': ...
                    elif option == 'realtime': ...
                    elif option == 'fadein': animfile.fade_in_time = next(optionsiter)
                    elif option == 'fadeout': animfile.fade_out_time = next(optionsiter)
                    elif option == 'weightlist': animfile.weight_list_name = next(optionsiter)
                    elif option == 'localhierarchy':
                        ...
                    elif option == 'compress':
                        frameskip: int = next(optionsiter)
                        ...
                    elif option == 'posecycle':
                        pose_parameter: str = next(optionsiter)
                        animfile.poseParam = pose_parameter
                    elif option == 'delta': animfile.delta = True
                    elif option == 'predelta': ...
                    elif option == 'blend':
                        blend_name: str = next(optionsiter)
                        _min: float = next(optionsiter)
                        _max: float = next(optionsiter)
                        animfile.poseParam = blend_name
                    elif option == 'blendwidth':
                        width: int = next(optionsiter)
                        ...
                    elif option == 'blendref':
                        ref: str = next(optionsiter)
                        ...
                    elif option == 'calcblend':
                        _name: str = next(optionsiter)
                        _attachment: str = next(optionsiter)
                        _idk: Literal["XR"] | Literal["YR"] | Literal["ZR"] = next(optionsiter)
                        ...
                    elif option == 'blendcenter':
                        center: str = next(optionsiter)
                        ...
                    elif option == 'ikrule': ...
                    elif option == 'iklock': ...
                    elif option == 'activitymodifier': ...
                    # Misc
                    elif option == 'node': ...
                    elif option == 'transition': ...
                    elif option == 'rtransition': ...
                    elif option == '$skiptransition': ...
                    elif option == 'keyvalues': ...

                for af in animfiles:
                    vmdl.add_to_appropriate_list(af)

        elif isinstance(command, (QC.weightlist, QC.defaultweightlist)):
            command: QC.weightlist
            if isinstance(command, QC.defaultweightlist):
                command.name = DEFAULT_WEIGHTLIST_NAME
                bHasDefaultWeightlist = True
            weightlist = ModelDoc.WeightList(name = command.name)
            optionsiter = iter(command.options)
            for bone, weight in zip(optionsiter, optionsiter):
                weightlist.weights.append(
                    dict(bone=bone_name_fixup(bone), weight=weight)
)
            vmdl.add_to_appropriate_list(weightlist)

        # https://developer.valvesoftware.com/wiki/$bodygroup
        elif isinstance(command, QC.bodygroup):
            command: QC.bodygroup
            bodygroup = ModelDoc.BodyGroup(name=command.name)
            
            # ['studio', 'mybody', 'studio', 'myhead', 'studio', 'b.smd','blank']
            optionsiter = iter(command.options)
            while string:=next(optionsiter, False):
                if string == "studio":
                    qc_choice = next(optionsiter)
                    if qc_choice.endswith(".smd"):
                        choice_name = Path(qc_choice).stem
                        add_rendermesh(choice_name, qc_choice)
                    else:
                        choice_name = qc_choice
                    choice = ModelDoc.BodyGroupChoice()
                    choice.meshes.append(choice_name)
                    bodygroup.add_nodes(choice)
                elif string == "blank":
                    bodygroup.add_nodes(ModelDoc.BodyGroupChoice(name="blank"))

            if IGNORE_SINGLEBODY_BODYGROUPS and len(bodygroup.children) == 1:
                # name the body after this bodygroup
                vmdl.base_lists[ModelDoc.RenderMeshList].children[-1].name = bodygroup.name
                continue

            vmdl.add_to_appropriate_list(bodygroup)
        
        # https://developer.valvesoftware.com/wiki/$cdmaterials
        elif isinstance(command, QC.cdmaterials):
            command: QC.cdmaterials
            if cdmaterials:
                continue
            cdmaterials = command.folder
            _log(f"  [material] cdmaterials = '{cdmaterials}', SMD names = {sorted(material_names)}")
            defaultmaterialgroup = ModelDoc.DefaultMaterialGroup()
            for material in sorted(material_names):
                to = fixup_material_path(material)
                defaultmaterialgroup.remaps.append(
                    {
                        "from": material,
                        "to": to,
                    }
                )
                if material.lower() != Path(to).stem.lower():
                    _log(f"  [material] REMAP: '{material}' → '{to}'")
            vmdl.add_to_appropriate_list(defaultmaterialgroup)

        # https://developer.valvesoftware.com/wiki/$texturegroup
        elif isinstance(command, QC.texturegroup):
            command: QC.texturegroup
            if len(command.options) < 2:
                continue
            defaultgroup = command.options[0]

            for skin_no, skin in enumerate(command.options[1:], 1):
                materialgroup = ModelDoc.MaterialGroup(
                    name = f"{command.name}_{skin_no}",
                )
                for i, default_mat in enumerate(defaultgroup):
                    if len(skin) <= i:
                        break
                    materialgroup.remaps.append(
                    {
                        "from": fixup_material_path(default_mat),
                        "to": fixup_material_path(skin[i], is_path=True),
                    }
                )
                vmdl.add_to_appropriate_list(materialgroup)

        # https://developer.valvesoftware.com/wiki/$renamematerial
        elif isinstance(command, QC.renamematerial):
            command: QC.renamematerial
            mgList = vmdl.base_lists.get(ModelDoc.MaterialGroupList)
            if mgList is None:
                continue

            dmg = mgList.find_by_class_bfs(ModelDoc.DefaultMaterialGroup)
            if dmg is None:
                continue
            
            # rename the s2 filename in default material group
            for remap in dmg.remaps:
                if remap["from"] != command.current:
                    continue
                remap["to"] = fixup_material_path(command.new)
                # then update any subsequent s2 links to the new one
                for mg in mgList.children:
                    if mg is dmg:
                        continue
                    for remap in mg.remaps:
                        if remap["from"] != fixup_material_path(command.current):
                            continue
                        remap["from"] = fixup_material_path(command.new)

        # https://developer.valvesoftware.com/wiki/$lod
        elif isinstance(command, QC.lod):
            command: QC.lod
            
            replacemodel = {}

            optionsiter = iter(command.options)
            while string:=next(optionsiter, False):
                if string == "replacemodel":
                    replacemodel.__setitem__(next(optionsiter), next(optionsiter))
                elif string == "removemodel":
                    replacemodel.__setitem__(next(optionsiter), None)
                elif string in ("replacematerial", "removemesh", "nofacial", "bonetreecollapse", "replacebone"):
                    ...
            # first LOD!
            if ModelDoc.LODGroupList not in vmdl.base_lists:
                lod0 = ModelDoc.LODGroup()
                ... # Form it based on the $body stuff
                vmdl.add_to_appropriate_list(lod0)
            
            # add stuff to lod0 that lodn is supposed to replace
            for lod0_mesh in replacemodel.keys():
                if lod0_mesh in lod0.meshes:
                    continue
                lod0.meshes.append(lod0_mesh)

            lod_n = ModelDoc.LODGroup(switch_threshold=command.threshold)
            for lod_n_mesh in replacemodel.values():
                if lod_n_mesh is None:
                    continue
                lod_n.meshes.append(lod_n_mesh)
            
            vmdl.add_to_appropriate_list(lod_n)

        # https://developer.valvesoftware.com/wiki/$attachment
        elif isinstance(command, QC.attachment):
            command: QC.attachment
            attachment = ModelDoc.Attachment(
                name = command.name,
                parent_bone = bone_name_fixup(command.parent_bone),
                relative_origin = [command.x, command.y, command.z],
                # TODO: rotation
            )
            vmdl.add_to_appropriate_list(attachment)

        # https://developer.valvesoftware.com/wiki/$collisionmodel
        elif isinstance(command, QC.collisionmodel):
            command: QC.collisionmodel
            physicsmeshfile = ModelDoc.PhysicsHullFile(
                filename=fixup_filepath(command.mesh_filename),
                surface_prop=global_surfaceprop
            )

            vmdl.add_to_appropriate_list(physicsmeshfile)
        
        # https://developer.valvesoftware.com/wiki/$collisionjoints
        elif isinstance(command, QC.collisionjoints):
            command: QC.collisionjoints
            physicsmeshfile = ModelDoc.PhysicsHullFile(
                filename=fixup_filepath(command.mesh_filename),
                surface_prop=global_surfaceprop
            )

            vmdl.add_to_appropriate_list(physicsmeshfile)
        
        # https://developer.valvesoftware.com/wiki/$includemodel
        # grab $animation, $sequence, $attachment and $collisiontext from this model
        elif isinstance(command, QC.includemodel):
            command: QC.includemodel
            vmdl.root.base_model_name = (models / command.filename).with_suffix('.vmdl').as_posix()
        
        elif isinstance(command, QC.declaresequence):
            sequences_declared.append(command.name)
        
        elif isinstance(command, QC.definebone):
            command: QC.definebone
            # bone already defined, ignore
            bone_name = bone_name_fixup(command.name)
            parent_bone_name = bone_name_fixup(command.parent)
            if skeleton.find_by_name_dfs(bone_name):
                continue
            bone = ModelDoc.Bone(
                name = bone_name,
                origin=[command.posx, command.posy, command.posz],
                angles=[command.rotx, command.roty, command.rotz],
            )
            # unparented bone
            if not command.parent:
               skeleton.children.append(bone)
            else:
                # parented to a bone that can't have been declared yet
                if not len(skeleton.children):
                    continue
                # parented to a bone that can't be found on the tree yet
                found = skeleton.find_by_name_dfs(parent_bone_name)
                if not found:
                    continue
                found.add_nodes(bone)
        
        # https://developer.valvesoftware.com/wiki/$bbox
        elif isinstance(command, (QC.bbox, QC.cbox)):
            command: Union[QC.bbox, QC.cbox]
            if IGNORE_BBOX:
                continue
            if isinstance(command, QC.bbox):
                hull_type = ModelDoc.Bounds_Hull
            else:
                hull_type = ModelDoc.Bounds_View
                # If the coordinates of the this clipping bounding box are all zero, $bbox is used instead.
                if not any(param != 0 for param in command.__dict__.values()):
                    # Don't even bother
                    continue

            vmdl.add_to_appropriate_list(hull_type(
                name = command.__class__.__name__,
                mins = [command.minx, command.miny, command.minz],
                maxs = [command.maxx, command.maxy, command.maxz],
            ))


        # https://developer.valvesoftware.com/wiki/$keyvalues
        elif isinstance(command, QC.keyvalues):
            for key, value in command.__dict__.items():
                key = key.lower().strip('"')
                # https://developer.valvesoftware.com/wiki/Prop_data
                if key == "prop_data":
                    prop_data = ModelDoc.GenericGameData(game_class="prop_data")
                    prop_data.game_keys.update(value)
                    vmdl.add_to_appropriate_list(prop_data)

    bIsIncludeFile = False
    if qc_path.suffix == ".qci":
        bIsIncludeFile = True
    
    if not model_name and not bIsIncludeFile:
        raise QCParseError("No model name found in QC file %s" % qc_path.local)
    
    if bIsIncludeFile:
        out_vmdl_path = sh.output(qc_path, '.vmdl_prefab')
    else:
        out_vmdl_path = sh.EXPORT_CONTENT / (models / model_name.lower()).with_suffix('.vmdl').as_posix()
    
    if not SHOULD_OVERWRITE and out_vmdl_path.exists():
        sh.skip("already-exist", out_vmdl_path)
        return

    out_vmdl_path.parent.MakeDir()

    if len(sequences_declared):
        vmdl_prefab = ModelDocVMDL()
        out_vmdl_prefab_path = out_vmdl_path.with_name("declared_sequences.vmdl_prefab")

        for sequence in sequences_declared:
            animfile = ModelDoc.AnimFile(
                name = sequence,
            )
            vmdl_prefab.add_to_appropriate_list(animfile)

        out_vmdl_prefab_path.write_text(vmdl_prefab.ToString())
        print('+ Saved prefab', out_vmdl_prefab_path.local)

    if len(skeleton.children):
        vmdl.root.add_nodes(skeleton)
        
    out_vmdl_path.write_text(vmdl.ToString())
    print('+ Saved', out_vmdl_path.local)


from dataclasses import asdict
class ModelDocVMDL(KV3File):
    def __init__(self):
        self.header = KV3Header(
            format='source1imported',
            format_ver='3cec427c-1b0e-4d48-a90a-0436f33a6041' if sh.SBOX else 'fb63b6ca-f435-4aa0-a2c7-c66ddc651dca'
        )
        self.root = ModelDoc.RootNode()

        self.base_lists: dict[Type[_BaseNode], _BaseNode] = {}

    def __str__(self):
        self["rootNode"] = asdict(self.root)
        return super().__str__()

    def add_to_appropriate_list(self, node: _Node):
        """
        Adds bodygroup to bodygrouplist, animfile to animationlist, etc. Only makes one list.
        """
        container_type = ModelDoc.get_container(type(node))
        container = self.base_lists.get(container_type)
        if container is None:
            if container_type is None:
                raise RuntimeError(f"Don't know where {type(node)} belongs.")
            container = container_type()
            self.base_lists[container_type] = container
            self.root.add_nodes(container)
        
        container.add_nodes(node)

if __name__ == "__main__":
    # TODO: Don't ask for src1?
    sh.parse_argv()
    main()
