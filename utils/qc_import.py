"""QC→VMDL import wrapper for sbox"""
import sys
sys.argv = [
    sys.argv[0],
    "-i", "F:/DevProject/Sbox/gmod解包/snpc",
    "-e", "F:/DevProject/Sbox/testzombie",
    "-b", "sbox",
]

import shared.base_utils2 as sh
sh.parse_argv()

import models_import as m
m.IMPORT_MDL = False
m.IMPORT_QC = True
m.COPY_FROM_SRC1_DIR = True
m.SHOULD_OVERWRITE = True
m.SAMPBOX = False
m.main()
