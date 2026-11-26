"""Process-local separate signed columns. No installed GAP mutation.
Retain all involution relators; avoid NEWTC's shared +/- augmented arrays.
This is an extraction safety change, not an assertion about index/termination.
"""

from .gap_sources import read


def bootstrap():
    source = read("sgpres.gi")
    part = source[
        source.index("NEWTC_DoCosetEnum:=function") : source.index(
            "#freegens,fgreerels,subgens,doaugmented,trace"
        )
    ]
    site = "if Length(w)=2 and Length(Set(w))=1 then"
    if part.count(site) != 1:
        raise ValueError("SIGNED_COLUMN_PATCH_SITE_CHANGED")
    return (
        part.replace(site, "if false then")
        + '\nPrint("DC_SIGNED_COLUMNS_SEPARATE_RELATORS_RETAINED\\n");\n'
    )
