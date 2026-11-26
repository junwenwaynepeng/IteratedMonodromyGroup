"""Render the proof-carrying NEWTC candidate with signed-column and secondary-word guards."""

import json
from pathlib import Path
from ..shared.exact import require, word


def render(data, raw_path, coset_cap):
    # All interpolation values are validated integers/JSON arrays, never shell text.
    require(type(data) is dict, "presentation object")
    r = data["rank"]
    d = data["degree"]
    require(
        type(r) is int and type(d) is int and 1 <= r <= 64 and 2 <= d <= 64,
        "presentation rank/degree",
    )
    for w in data["relators"] + data["subgroup_generators"]:
        word(w, r * d, 1000000)
    require(type(coset_cap) is int and 1 <= coset_cap <= 2147483647, "coset cap")
    arrays = json.dumps(
        [data["relators"], data["subgroup_generators"]], separators=(",", ":")
    )
    path = json.dumps(str(Path(raw_path).resolve()))
    script = """# Generated direct-cover candidate script; no action/relator claims originate in GAP.
# Process-local defense for GAP4.12.1 WordProductLetterRep argument aliasing.
# Installed system files remain unchanged. NEWTC internal global calls see this wrapper.
if GAPInfo.Version<>"4.12.1" then Error("PINNED_GAP_VERSION_MISMATCH");fi;
DCOriginalWordProductLetterRep:=WordProductLetterRep;
DCMutationControl:=function(f)
 local a,b,v;a:=[1];b:=[2];v:=CallFuncList(f,[[9],[-9],a,b]);
 return [v,a,b];
end;
DCOldAliasResult:=DCMutationControl(DCOriginalWordProductLetterRep);
if DCOldAliasResult<>[[1,2],[1,2],[2]] then Error("PINNED_WORDPRODUCT_ALIAS_REPRODUCTION_MISMATCH");fi;
Print("DC_OLD_ARGUMENT_MUTATION_REPRODUCED\\n");
DCWordProductSafe:=function(arg)
 if Length(arg)=0 then Error("WORDPRODUCT_REQUIRES_ARGUMENT");fi;
 return CallFuncList(DCOriginalWordProductLetterRep,List(arg,ShallowCopy));
end;
MakeReadWriteGlobal("WordProductLetterRep");
WordProductLetterRep:=DCWordProductSafe;
MakeReadOnlyGlobal("WordProductLetterRep");
DCArgumentControls:=function()
 local cases,v,before,out,i,shared;
 cases:=[ [[],[]], [[1]], [[],[1]], [[1],[]], [[1],[-1]],
          [[9],[-9],[1],[2]], [[1,2],[-2,-1],[],[3]],
          [[-1,-2],[2,1],[-3],[3]], [[1],[2],[-2],[-1]] ];
 shared:=[3];Add(cases,[[9],[-9],shared,shared]);
 for v in cases do
  before:=StructuralCopy(v);out:=CallFuncList(WordProductLetterRep,v);
  if v<>before then Error("WORDPRODUCT_ARGUMENT_MUTATED");fi;
  if out<>FreelyReducedLetterRepWord(Concatenation(v)) then Error("WORDPRODUCT_WRONG_PRODUCT");fi;
  Add(out,99999);
  if v<>before then Error("WORDPRODUCT_RETURN_ALIASES_ARGUMENT");fi;
 od;
 if DCMutationControl(WordProductLetterRep)<>[[1,2],[1],[2]] then Error("WORDPRODUCT_DEFENSE_FAILED");fi;
 Print("DC_ARGUMENT_COPY_CONTROLS_PASS\\n");
end;
DCArgumentControls();
DCMain:=function()
local data,F,fg,DCWord,rels,sub,aug,r,d,n,reps,queue,i,g,j,w,out,sec,z,x,b;
if GAPInfo.Version<>"4.12.1" then Error("PINNED_GAP_VERSION_MISMATCH");fi;
if not IsBound(NEWTC_CosetEnumerator) or not IsBound(NEWTC_Rewrite) then Error("PINNED_NEWTC_API_MISSING");fi;
Print("DC_READY GAP=",GAPInfo.Version,"\\n");
r:=%d;d:=%d;data:=%s;
F:=FreeGroup(r*d);fg:=GeneratorsOfGroup(F);
DCWord:=function(w) local a,g; a:=One(F);for g in w do a:=a*fg[AbsInt(g)]^SignInt(g);od;return a;end;
rels:=List(data[1],DCWord);sub:=List(data[2],DCWord);
aug:=NEWTC_CosetEnumerator(fg,rels,sub,true,false:limit:=%d,quiet:=true);
if aug=fail then Print("DC_LIMIT COSETS\\n");return;fi;
if not IsBound(aug.isNewAugmentedTable) or not aug.isNewAugmentedTable or aug.useAddition then Error("PINNED_NEWTC_RECORD_MISMATCH");fi;
if aug.subgword<>data[2] then Error("SUBGROUP_GENERATOR_ORDER_CHANGED");fi;
n:=aug.index;if n<1 or n>%d then Error("UNEXPECTED_COSET_COUNT");fi;
reps:=[];reps[1]:=[];queue:=[1];i:=1;
while i<=Length(queue) do
 x:=queue[i];
 for g in [1..r*d] do
  for b in [g,-g] do
   j:=aug.ct[aug.offset+b][x];
   if not IsBound(reps[j]) then reps[j]:=Concatenation(reps[x],[b]);Add(queue,j);fi;
  od;
 od;i:=i+1;
od;
if Length(queue)<>n then Error("COSET_GRAPH_DISCONNECTED");fi;
sec:=[];
if aug.secount>Length(sub) then
 for i in [Length(sub)+1..aug.secount] do
  if not IsBound(aug.secondary[i]) then Error("SECONDARY_DEFINITION_MISSING");fi;
  Add(sec,[i,aug.secondary[i]]);
 od;
fi;
out:=OutputTextFile(%s,false);SetPrintFormattingStatus(out,false);
PrintTo(out,"{\\"schema_version\\":1,\\"gap_version\\":\\"4.12.1\\",\\"rank\\":",r,",\\"degree\\":",d,",\\"primary_count\\":",Length(sub),",\\"secondary\\":",sec,",\\"representatives\\":",reps,",\\"transitions\\":[");
z:=false;
for i in [1..n] do
 for g in [1..r*d] do
  for b in [g,-g] do
   j:=aug.ct[aug.offset+b][i];w:=Concatenation(reps[i],[b],-Reversed(reps[j]));
   w:=NEWTC_Rewrite(aug,1,w,1);
   if z then PrintTo(out,",");fi;z:=true;
   x:=QuoInt(AbsInt(b)-1,r);# ambient generator mapping retains the signed input letter
   PrintTo(out,"[",i-1,",",x,",",SignInt(b)*(RemInt(AbsInt(b)-1,r)+1),",",j-1,",",w,"]");
  od;
 od;
od;
PrintTo(out,"]}\\n");CloseStream(out);Print("DC_EXPORTED\\n");
end;
DCMain();
Print("COMPLETE_PROTOCOL\\n");
QUIT;
""" % (
        r,
        d,
        arrays,
        coset_cap,
        coset_cap,
        path,
    )
    from .gap_sources import read

    read("wordrep.gi")
    from .gap_secondary_guard import bootstrap
    from .signed_column_guard import bootstrap as signed_bootstrap

    return script.replace(
        "DCMain:=function()", bootstrap() + signed_bootstrap() + "DCMain:=function()", 1
    )
