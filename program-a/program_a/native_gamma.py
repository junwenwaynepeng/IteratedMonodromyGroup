"""Construct GAP source for the supplied fundamental action."""

import json


def lit(x):
    return json.dumps(x, separators=(",", ":"))


def preamble():
    return (
        """SetPrintFormattingStatus("*stdout*",false);;
PAEvent:=function(s) Print("PA_INDEX ",s,"\\n");end;;
"""
        + 'if LoadPackage("fr")=fail then Error("FR_LOAD");fi;;\n'
    )


def model_data(model):
    q, d = len(model["roots"]), len(model["roots"][0])
    transitions = [
        [([] if v == 0 else [v]) if isinstance(v, int) else v for v in row]
        for row in model["sections"]
    ]
    return (
        "Q:"
        + "="
        + str(q)
        + ";;D:="
        + str(d)
        + ";;\nMT:="
        + lit(transitions)
        + ";;MR:="
        + lit([[i + 1 for i in row] for row in model["roots"]])
        + ";;\n"
    )


def machine(product=False):
    return (
        "M:=FRMachine(FreeGroup(Q*(D+1)),MT,MR);;\n"
        if product
        else "M:=FRMachine(FreeGroup(Q),MT,MR);;\n"
    )


def group():
    return """S:=List([1..Q],i->FRElement(M,[i]));;G:=Group(S);;
PAWord:=function(w)
 local a,i;a:=One(G);for i in w do a:=a*S[AbsInt(i)]^SignInt(i);od;return a;
end;;
PAEvent("MODEL_READY");;
"""


def original(model):
    return model_data(model) + machine() + group()
