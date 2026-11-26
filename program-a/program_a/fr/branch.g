PAEvent("FR_BRANCHING_SUBGROUP_ENTER");;
# Actual FR attribute, infinity-level search with package radius progression.
K_FR:=BranchingSubgroup(G);;
PAEvent("FR_BRANCHING_SUBGROUP_RETURNED");;
# BranchingSubgroup(G) is cached by GAP; IsBranched reuses this SAME K_FR.
if not HasBranchingSubgroup(G) then Error("BRANCHING_ATTRIBUTE_NOT_CACHED");fi;;
PAEvent("FR_IS_BRANCHED_INDEX_ENTER");;
ANSWER:=IsBranched(G);;
if ANSWER=true then PAEvent("FR_IS_BRANCHED_TRUE");
elif ANSWER=false then PAEvent("FR_IS_BRANCHED_FALSE");
else Error("UNEXPECTED_BRANCH_RESULT");fi;;
PAEvent("COMPLETE_PROTOCOL");; QuitGap(0);
