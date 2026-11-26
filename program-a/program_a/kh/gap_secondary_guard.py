"""Pinned process-local repair of NEWTC secondary free-word compression."""

from .gap_sources import read


def bootstrap():
    s = read("sgpres.gi")
    s = s[s.index("NEWTC_ModifiedCoincidence:=function") :]
    s = s[: s.index("# superseded by kernel function")]
    a = "if ForAll(DATA.secondary[i],x->x in ws) then"
    b = "DATA.secount:=DATA.secount+1;"
    if s.count(a) != 1 or s.count(b) != 1:
        raise ValueError("SECONDARY_PATCH_SITE_MISMATCH")
    s = s.replace(
        a,
        "if Length(DATA.secondary[i])>0 and ForAll(DATA.secondary[i],x->x in ws) then",
    )
    s = s.replace(b, "if Length(w)<=1 then return w;fi;\n    " + b)
    return s + "\n" + CONTROLS


CONTROLS = r"""DCSecondaryControls:=function()
 local D;
 D:=rec(subgens:=[1,2],secount:=3,secondary:=[],useAddition:=false,
 s:=[],p:=[1,2],pp:=[[],[]],ct:=[],aug:=[],offset:=0,A:=[],dead:=0);
 D.secondary[3]:=[1,2];
 NEWTC_ModifiedCoincidence(D,2,1,[1,2,-3]);
 if D.secount<>3 then Error("SECONDARY_EMPTY_WORD_STORED");fi;
 D:=rec(subgens:=[1,2],secount:=3,secondary:=[],useAddition:=false,
 s:=[],p:=[1,2],pp:=[[],[]],ct:=[],aug:=[],offset:=0,A:=[],dead:=0);
 D.secondary[3]:=[];
 NEWTC_ModifiedCoincidence(D,2,1,[1,2]);
 if D.secount<>4 or D.secondary[4]<>[1,2] then Error("SECONDARY_EMPTY_PATTERN_NOT_SKIPPED");fi;
 Print("DC_SECONDARY_EMPTY_WORD_CONTROLS_PASS\n");
end;
DCSecondaryControls();
"""
