"""Independent proof-carrying Felsch enumeration in GAP.
Each edge is r_i*g = tuple_word*r_j; UF weights are r_i=weight*r_parent.
All inputs are verified outside GAP. No NEWTC augmented table/secondary mapping.
"""

import json, hashlib
from pathlib import Path
from .exact import require, word


def render(data, raw_path, coset_cap):
    r = data["rank"]
    d = data["degree"]
    require(
        type(r) is int and type(d) is int and 1 <= r <= 64 and 2 <= d <= 64,
        "Proof TC dimensions",
    )
    require(type(coset_cap) is int and 1 <= coset_cap, "Proof TC coset bound")
    for v in data["relators"] + data["subgroup_generators"]:
        word(v, r * d, 1000000)
    context = data.get("progress_context")
    if context is not None:
        require(
            type(context) is dict
            and set(context)
            == {"subgroup_label", "native_attempt_id", "subgroup_epoch"},
            "Telemetry context fields",
        )
        from .table_telemetry import validate_progress

        validate_progress(
            {
                "stage": "FELSCH_TABLE_PROGRESS",
                "schema_version": 1,
                "current_representatives": 1,
                "ambient_positive_generators": r * d,
                "signed_columns": 2 * r * d,
                "established_transitions": 0,
                "unfilled_transitions": 2 * r * d,
                "total_transition_slots": 2 * r * d,
                "phase": "initialization",
                "native_cpu_ms": 0,
                "native_elapsed_ms": 0,
                "table_complete": False,
                "evidence": "NATIVE_PARTIAL_DIAGNOSTIC",
                "sample_sequence": 1,
                "snapshot_status": "NOT_DUE",
                **context,
            }
        )
    context_text = (
        json.dumps(context, separators=(",", ":"))[1:-1] if context is not None else ""
    )
    return (
        SCRIPT.replace(
            "@TELEMETRY_ENABLED@", "true" if context is not None else "false"
        )
        .replace("@CONTEXT@", json.dumps(context_text))
        .replace(
            "@DATA@",
            json.dumps(
                [data["relators"], data["subgroup_generators"]], separators=(",", ":")
            ),
        )
        .replace(
            "@DEBUG@", "true" if data.get("diagnostic_partial", False) else "false"
        )
        .replace("@R@", str(r))
        .replace("@D@", str(d))
        .replace("@CAP@", str(coset_cap))
        .replace("@OUT@", json.dumps(str(Path(raw_path).resolve())))
    )


SCRIPT = r"""DCMain:=function()
local data,r,d,m,cap,offset,letters,n,live,peak,p,weight,ct,proof,queue,head,changed,limited,
 Progress,Snapshot,Column,rowFilled,rowGroups,established,groupCount,telemetryEnabled,telemetryContext,telemetryOrigin,telemetryLast,telemetrySnapshotLast,telemetrySequence,telemetryCountsBytes,telemetrySnapshotBytes,telemetryOps,telemetryStopped,
 Prod,Inv,Find,Edge,Merge,Put,Drain,Scan,Report,Define,Ambient,Partial,repParent,repLetter,debug,snapdone,occ,events,eventhead,cursorRoot,rel,sgn,pos,i,j,g,v,f,b,k,ri,z,found,roots,reps,U,order,id,out,first,idx,x;
if GAPInfo.Version<>"4.12.1" then Error("PINNED_GAP_VERSION_MISMATCH");fi;
r:=@R@;d:=@D@;m:=r*d;cap:=@CAP@;offset:=m+1;data:=@DATA@;
debug:=@DEBUG@;snapdone:=false;repParent:=[0];repLetter:=[0];
letters:=Concatenation([1..m],-[1..m]);n:=1;live:=1;peak:=1;p:=[1];weight:=[[]];ct:=[ListWithIdenticalEntries(2*m+1,0)];proof:=[[]];queue:=[];head:=1;events:=[];eventhead:=1;changed:=0;limited:=false;cursorRoot:=1;occ:=List([1..2*m+1],i->[]);
# Read-only diagnostics: no Find/Edge/Prod and no table-wide per-tick scans.
telemetryEnabled:=@TELEMETRY_ENABLED@;telemetryContext:=@CONTEXT@;
rowFilled:=[0];groupCount:=Minimum(8,2*m);rowGroups:=[ListWithIdenticalEntries(groupCount,0)];established:=0;
telemetryOrigin:=NanosecondsSinceEpoch();telemetryLast:=telemetryOrigin-2000000000;
telemetrySnapshotLast:=telemetryOrigin-30000000000;telemetrySequence:=0;
telemetryCountsBytes:=0;telemetrySnapshotBytes:=0;telemetryOps:=0;telemetryStopped:=false;
Column:=function(h) if h>0 then return h-1;else return m-h-1;fi;end;
Snapshot:=function()
 local entries,root,position,column,h,target,rowBands,counts,band,bc,rs,re,cs,ce,filled,missing,body,item;
 entries:=[];position:=0;
 if 2*m*live<=256 then
  for root in [1..n] do if p[root]=root then
   for column in [0..2*m-1] do
    if column<m then h:=column+1;else h:=-(column-m+1);fi;
    target:=ct[root][offset+h];
    if target=0 then item:="null";else
     while p[target]<>target do target:=p[target];od;
     item:=String(target);
    fi;
    Add(entries,Concatenation("[",String(position),",",String(root),",",String(column),",",String(h),",",item,"]"));
   od;position:=position+1;
  fi;od;
  body:=Concatenation("\"mode\":\"cells\",\"cells\":[",JoinStringsWithSeparator(entries,","),"]");
 else
  # Eight fixed signed-column groups, eight live-root bands: at most64 bins.
  # This scans current root flags and <=8 counters/root once per30s,
  # never the potentially819,200,000 individual transition slots.
  rowBands:=Minimum(8,live);counts:=List([1..rowBands],i->ListWithIdenticalEntries(groupCount,0));
  for root in [1..n] do if p[root]=root then
   band:=QuoInt(position*rowBands,live)+1;
   for bc in [1..groupCount] do counts[band][bc]:=counts[band][bc]+rowGroups[root][bc];od;
   position:=position+1;
  fi;od;
  for band in [0..rowBands-1] do
   rs:=QuoInt(band*live+rowBands-1,rowBands);re:=QuoInt((band+1)*live+rowBands-1,rowBands);
   for bc in [0..groupCount-1] do
    cs:=QuoInt(bc*2*m+groupCount-1,groupCount);ce:=QuoInt((bc+1)*2*m+groupCount-1,groupCount);
    filled:=counts[band+1][bc+1];missing:=(re-rs)*(ce-cs)-filled;
    Add(entries,Concatenation("{\"row_start\":",String(rs),",\"row_end\":",String(re),",\"col_start\":",String(cs),",\"col_end\":",String(ce),",\"established\":",String(filled),",\"unfilled\":",String(missing),"}"));
   od;
  od;
  body:=Concatenation("\"mode\":\"bins\",\"bins\":[",JoinStringsWithSeparator(entries,","),"]");
 fi;
 return Concatenation("{\"schema_version\":1,",telemetryContext,",\"sample_sequence\":",String(telemetrySequence),",",body,"}");
end;
Progress:=function(phase,force)
 local now,elapsed,cpu,base,snap,kind,line,charge,complete;
 if not telemetryEnabled or (limited<>false and limited<>"COSETS") then return;fi;
 telemetryOps:=telemetryOps+1;
 if not force and RemInt(telemetryOps,32)<>0 then return;fi;
 now:=NanosecondsSinceEpoch();
 if (telemetryStopped or now-telemetryLast<2000000000)and not force then return;fi;
 telemetrySequence:=telemetrySequence+1;elapsed:=QuoInt(now-telemetryOrigin,1000000);cpu:=Runtime();
 if phase="complete" then complete:="true";else complete:="false";fi;
 base:=Concatenation("{\"stage\":\"FELSCH_TABLE_PROGRESS\",\"schema_version\":1,",telemetryContext,",\"sample_sequence\":",String(telemetrySequence),",\"current_representatives\":",String(live),",\"ambient_positive_generators\":",String(m),",\"signed_columns\":",String(2*m),",\"established_transitions\":",String(established),",\"unfilled_transitions\":",String(2*m*live-established),",\"total_transition_slots\":",String(2*m*live),",\"phase\":\"",phase,"\",\"native_cpu_ms\":",String(cpu),",\"native_elapsed_ms\":",String(elapsed),",\"table_complete\":",complete,",\"evidence\":\"NATIVE_PARTIAL_DIAGNOSTIC\"");
 kind:="NOT_DUE";snap:="";
 if now-telemetrySnapshotLast>=30000000000 or phase="complete" then
  if telemetrySnapshotBytes<1572864-32768 then
   snap:=Snapshot();charge:=2*Length(snap)+128;
   if charge+telemetrySnapshotBytes<=1572864 then
    telemetrySnapshotBytes:=telemetrySnapshotBytes+charge;telemetrySnapshotLast:=now;
    if 2*m*live<=256 then kind:="CELLS";else kind:="BINS";fi;
    snap:=Concatenation(",\"table_snapshot\":",snap);
   else snap:="";kind:="BUDGET_EXHAUSTED";fi;
  else kind:="BUDGET_EXHAUSTED";fi;
 fi;
 charge:=2*Length(base)+512;
 if telemetryCountsBytes+charge>2621440-8192 then
  if telemetryStopped and phase<>"complete" then return;fi;
  telemetryStopped:=true;base:=Concatenation(base,",\"telemetry_status\":\"BYTE_BUDGET_EXHAUSTED\"");
 fi;
 telemetryCountsBytes:=telemetryCountsBytes+charge;telemetryLast:=now;
 line:=Concatenation("DC_TABLE_PROGRESS ",base,",\"snapshot_status\":\"",kind,"\"",snap,"}\n");Print(line);
end;
Progress("initialization",true);
for rel in data[1] do
 for v in [rel,-Reversed(rel)] do
  for pos in [1..Length(v)] do Add(occ[offset+v[pos]],[v,pos]);Progress("initialization",false);od;
 od;
od;
Inv:=w->-Reversed(w);
Prod:=function(arg)
 local ans,w,before;
 ans:=[];
 for w in arg do ans:=FreelyReducedLetterRepWord(Concatenation(ans,w));
  if Length(ans)>100000 then limited:="PROOF_WORD_LENGTH";return [];fi;
 od;

 return ans;
end;
if Prod([1,2],[-2,3])<>[1,3] or Prod([1,2],[-2,-1])<>[] then Error("FACTOR_PRODUCT_CONTROL");fi;
Print("DC_FACTOR_PRODUCT_CONTROLS_PASS\nDC_READY GAP=",GAPInfo.Version,"\n");
Find:=function(a)
 local acc,path,root,node;path:=[];root:=a;
 while p[root]<>root do Add(path,root);root:=p[root];od;
 acc:=[];for node in Reversed(path) do acc:=Prod(weight[node],acc);p[node]:=root;weight[node]:=acc;od;
 return [root,acc];
end;
Edge:=function(a,g)
 local fa,j,fb,v;
 fa:=Find(a);j:=ct[fa[1]][offset+g];
 if j=0 then return fail;fi;
 fb:=Find(j);v:=Prod(proof[fa[1]][offset+g],fb[2]);
 ct[fa[1]][offset+g]:=fb[1];proof[fa[1]][offset+g]:=v;
 return [fb[1],Prod(fa[2],v)];
end;
Merge:=function(a,b,v)
 local fa,fb,w,hi,lo,h;
 if limited<>false then return;fi;
 fa:=Find(a);fb:=Find(b);if fa[1]=fb[1] then return;fi;
 w:=Prod(Inv(fa[2]),v,fb[2]);
 if fa[1]>fb[1] then hi:=fa[1];lo:=fb[1];else hi:=fb[1];lo:=fa[1];w:=Inv(w);fi;
 p[hi]:=lo;weight[hi]:=w;live:=live-1;changed:=changed+1;
 established:=established-rowFilled[hi];rowFilled[hi]:=0;rowGroups[hi]:=ListWithIdenticalEntries(groupCount,0);
 for h in letters do
  if ct[hi][offset+h]<>0 then Add(queue,[hi,h,ct[hi][offset+h],proof[hi][offset+h]]);Add(events,[hi,h]);Add(events,[ct[hi][offset+h],-h]);fi;
 od;
 ct[hi]:=[];proof[hi]:=[];Progress("merge",false);
end;
Put:=function(a,g,b,v)
 local fa,fb,w,e;
 if limited<>false then return;fi;
 fa:=Find(a);fb:=Find(b);w:=Prod(Inv(fa[2]),v,fb[2]);e:=Edge(fa[1],g);
 if e=fail then
  ct[fa[1]][offset+g]:=fb[1];proof[fa[1]][offset+g]:=w;changed:=changed+1;
  rowFilled[fa[1]]:=rowFilled[fa[1]]+1;established:=established+1;
  rowGroups[fa[1]][QuoInt(Column(g)*groupCount,2*m)+1]:=rowGroups[fa[1]][QuoInt(Column(g)*groupCount,2*m)+1]+1;
  Add(queue,[fb[1],-g,fa[1],Inv(w)]);Add(events,[fa[1],g]);Progress("definition",false);
 else Merge(e[1],fb[1],Prod(Inv(e[2]),w));fi;
end;
Drain:=function()
 local row,event,position,rot;
 while (head<=Length(queue) or eventhead<=Length(events)) and limited=false do
  Progress("drain",false);
  if head<=Length(queue) then row:=queue[head];head:=head+1;Put(row[1],row[2],row[3],row[4]);
  else
   event:=events[eventhead];eventhead:=eventhead+1;
   for position in occ[offset+event[2]] do
    rot:=Concatenation(position[1]{[position[2]..Length(position[1])]},position[1]{[1..position[2]-1]});
    Scan(event[1],rot,event[1],[]);Progress("drain",false);
    if limited<>false then break;fi;
   od;
  fi;
 od;
 queue:=[];head:=1;events:=[];eventhead:=1;
end;
Scan:=function(a,w,b,y)
 local left,right,front,back,fp,bp,e,fa,fb;
 front:=a;back:=b;fp:=[];bp:=[];left:=1;right:=Length(w);
 while left<=right do
  e:=Edge(front,w[left]);if e=fail then break;fi;
  fp:=Prod(fp,e[2]);front:=e[1];left:=left+1;Progress("scan",false);
 od;
 while right>=left do
  e:=Edge(back,-w[right]);if e=fail then break;fi;
  bp:=Prod(bp,e[2]);back:=e[1];right:=right-1;Progress("scan",false);
 od;
 if right<left then Merge(front,back,Prod(Inv(fp),y,bp));
 elif right=left then Put(front,w[left],back,Prod(Inv(fp),y,bp));fi;
end;
Report:=function()
 Print("DC_COUNTS ",n," ",live," ",peak,"\n");
 if limited<>false then Progress("limited",true);Print("DC_LIMIT ",limited,"\n");fi;
end;
Ambient:=function(a)
 local v;v:=[];while a<>1 do Add(v,repLetter[a]);a:=repParent[a];od;return Reversed(v);
end;
Partial:=function()
 local os,a,h,e,rows,batch,item;
 rows:=[];
 for a in [1..n] do
  if p[a]=a then
   for h in letters do
    e:=Edge(a,h);
    if e<>fail and Length(e[2])>0 and Length(e[2])<=1000 then Add(rows,[Ambient(a),h,Ambient(e[1]),e[2]]);fi;
    if Length(rows)>=32 then break;fi;
   od;
  fi;
  if Length(rows)>=32 then break;fi;
 od;
 os:=OutputTextFile(@OUT@,false);SetPrintFormattingStatus(os,false);
 PrintTo(os,"{\"schema_version\":1,\"kind\":\"proof_tc_partial_diagnostic_v1\",\"rank\":",r,",\"degree\":",d,",\"primary_count\":",Length(data[2]),",\"created_cosets\":",n,",\"live_cosets\":",live,",\"peak_cosets\":",peak,",\"edges\":",rows,"}");CloseStream(os);
 Print("DC_PARTIAL_DIAGNOSTIC_EXPORTED\n");
end;
Define:=function(a,g)
 if n>=cap then limited:="COSETS";return;fi;
 n:=n+1;live:=live+1;peak:=Maximum(peak,live);repParent[n]:=a;repLetter[n]:=g;p[n]:=n;weight[n]:=[];rowFilled[n]:=0;rowGroups[n]:=ListWithIdenticalEntries(groupCount,0);ct[n]:=ListWithIdenticalEntries(2*m+1,0);proof[n]:=[];
 Progress("definition",false);Put(a,g,n,[]);Drain();if debug and not snapdone and n>=25 and limited=false then Partial();snapdone:=true;fi;if RemInt(n,25)=0 then Report();fi;
end;
# Install subgroup loops once, carrying their original primary generator IDs.
for k in [1..Length(data[2])] do
 while limited=false do
  Scan(1,data[2][k],1,[k]);Drain();
  i:=1;found:=false;
  for g in data[2][k] do
   z:=Edge(i,g);
   if z=fail then found:=[i,g];break;fi;
   i:=z[1];
  od;
  if found=false then break;fi;
  Define(found[1],found[2]);
 od;
 if limited<>false then Report();return;fi;
od;
# Fair Felsch definitions; each new/transported edge triggers all cyclic relator scans.
while true do
 found:=false;
 while cursorRoot<=n do
  if p[cursorRoot]=cursorRoot then
   for g in letters do if Edge(cursorRoot,g)=fail then found:=[cursorRoot,g];break;fi;od;
  fi;
  if found<>false then break;fi;
  cursorRoot:=cursorRoot+1;
 od;
 if found=false then break;fi;
 Define(found[1],found[2]);
 if limited<>false then Report();return;fi;
od;
# Select GAP's own BFS representatives and transport UF edge witnesses.
reps:=[];U:=[];order:=[1];id:=[];id[1]:=1;reps[1]:=[];U[1]:=[];idx:=1;
while idx<=Length(order) do
 i:=order[idx];
 for g in letters do
  z:=Edge(i,g);j:=z[1];
  if not IsBound(id[j]) then Add(order,j);id[j]:=Length(order);reps[id[j]]:=Concatenation(reps[idx],[g]);U[id[j]]:=Prod(U[idx],z[2]);fi;
 od;
 idx:=idx+1;
od;
if Length(order)<>live then Error("PROOF_TC_DISCONNECTED");fi;
if limited<>false then Report();return;fi;
out:=OutputTextFile(@OUT@,false);SetPrintFormattingStatus(out,false);
PrintTo(out,"{\"schema_version\":1,\"kind\":\"proof_tc_complete_v1\",\"gap_version\":\"4.12.1\",\"rank\":",r,",\"degree\":",d,",\"primary_count\":",Length(data[2]),",\"secondary\":[],\"representatives\":",reps,",\"transitions\":[");
first:=true;
for idx in [1..Length(order)] do
 i:=order[idx];
 for g in letters do
  z:=Edge(i,g);j:=id[z[1]];v:=Prod(U[idx],z[2],Inv(U[j]));
  if limited<>false then CloseStream(out);Report();return;fi;
  if not first then AppendTo(out,",");fi;first:=false;x:=QuoInt(AbsInt(g)-1,r);
  AppendTo(out,"[",idx-1,",",x,",",SignInt(g)*(RemInt(AbsInt(g)-1,r)+1),",",j-1,",",v,"]");
 od;
od;
AppendTo(out,"]}\n");CloseStream(out);Progress("complete",true);Report();Print("DC_EXPORTED\n");
end;
DCMain();Print("COMPLETE_PROTOCOL\n");QUIT;
"""
