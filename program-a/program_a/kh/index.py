"""Render Index(P,K) with P the faithful coordinate product."""

from ..native_gamma import lit
from ..shared.exact import validate_model, word, require
from ..fr import prefix


def render(packet, tuples=None):
    _, rank, degree = validate_model(packet)
    for row in tuples or []:
        word(row["parent_word"], rank)
        require(len(row["sections"]) == degree, "tuple degree")
        for section in row["sections"]:
            word(section, rank)
    source = prefix(packet)
    source += """PAEvent("PRODUCT_AMBIENT_ENTER");;
    PAEmbeddedGenerators:=Concatenation(List([1..D],x->List(S,g->VertexElement(x,g))));;
    P:=Group(PAEmbeddedGenerators);;
    """
    if tuples is None:
        source += """PAEvent("FRESH_EXACT_ROOT_STABILIZER_ENTER");;
    ST:=Stabilizer(G,[1..D],OnTuples);;
    T:=List(GeneratorsOfGroup(ST),g->DecompositionOfFRElement(g));;
    if not ForAll(T,t->t[2]=[1..D]) then Error("ROOT_STABILIZER_MISMATCH");fi;;
    KG:=List(T,t->Product([1..D],x->VertexElement(x,t[1][x])));;
    """
    if tuples is not None:
        # Input identity is checked in GAP on original whole-tree elements.
        source += "PW:=" + lit([t["parent_word"] for t in tuples]) + ";;\n"
        source += "SW:=" + lit([t["sections"] for t in tuples]) + ";;\n"
        source += """PAEvent("FROZEN_TUPLES_VALIDATION_ENTER");;
    KG:=[];; de:=fail;;
    for i in [1..Length(PW)] do
     de:=DecompositionOfFRElement(PAWord(PW[i]));;
     if de[2]<>[1..D] then Error("TUPLE_PARENT_NOT_ROOT_FIXING");fi;
     if not ForAll([1..D],x->de[1][x]=PAWord(SW[i][x])) then Error("TUPLE_SECTION_MISMATCH");fi;
     Add(KG,Product([1..D],x->VertexElement(x,PAWord(SW[i][x]))));
    od;
    """
    source += """if Length(KG)=0 then K_GAP:=TrivialSubgroup(P);else K_GAP:=Subgroup(P,KG);fi;;
    PAEvent("GAP_INDEX_ENTER");;
    IDX:=Index(P,K_GAP);;
    if IsInt(IDX) and IDX>=1 then Print("PA_INDEX FINITE_INDEX ",IDX,"\\n");
    elif IDX=infinity then PAEvent("INFINITE_INDEX");
    elif IDX=fail then PAEvent("INDEX_UNDECIDED");
    else Error("UNEXPECTED_INDEX_RESULT");fi;;
    """
    return source + 'PAEvent("COMPLETE_PROTOCOL");; QuitGap(0);\n'
