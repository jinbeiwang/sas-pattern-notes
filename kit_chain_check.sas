/*********************************************************************
*  kit_chain_check.sas
*
*  Self-contained check for the chained kit replacement step
*  (ECREFID / ECLOT / BATCHNUM, SAS hash object).
*
*  Base SAS only: no study macros, no external libraries, no formats.
*  Every input row is synthetic and lives in this file.
*
*  To run : sas kit_chain_check.sas      (or open it and press Submit)
*  To pass: the log ends with
*             "kit chain check: <n> checks, <n> pass, 0 fail"
*
*  The last block (the S14 conflict) is expected to stop with an ERROR.
*  That is the guardrail firing, not a defect. Set demo_conflict = N to
*  skip it.
*
*  Cases that are deliberately not here, so that a reader does not go
*  looking for them:
*    - a chain of eight hops: the same step at three, and the longest
*      chain the extract has shown is three;
*    - a kit whose pointer names itself: the cycle of S07 already
*      covers "the walk never reaches a terminal record";
*    - a row with no kit type, and a visit label the two sides of the
*      join spell differently: both are settled before this step sees
*      the data (the split's guard and the clinical-side mapping), so
*      they are pipeline tests, not chain tests.
*--------------------------------------------------------------------*/

%let demo_conflict = Y;      /* Y: run the block that must fail       */
%let vol_subjects  = 2000;   /* S15 volume case; 0 to skip it         */
%let vol_visits    = 4;
%let vol_links     = 3;      /* replacements per visit; 3 is the most */
                             /* any subject has shown                 */

%let cases = S01 S02 S03 S05 S06 S07 S09 S10 S11 S12 S17;

*--------------------------------------------------------------------*;
*  Fixture: one pipe-separated line per row of the IRT extract       *;
*  case|rowid|scn_num|kit_num|lot_num|btch_num|vis_type|kit_tyds|kitnumrp
*  A "." in kitnumrp is numeric missing, so that kit is terminal.     *;
*--------------------------------------------------------------------*;
data raw_kit;
     length case $3 vis_type $20 kit_tyds $8 lot_num $10 btch_num $10;
     infile datalines dlm = '|' dsd truncover;
     input case $ rowid scn_num kit_num lot_num $ btch_num $ vis_type $ kit_tyds $ kitnumrp;
datalines;
S01|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|.
S02|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S02|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|.
S03|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S03|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1003
S03|3|101|1003|LOT-C|B03|KIT REPLACEMENT|KIT|1004
S03|4|101|1004|LOT-D|B04|KIT REPLACEMENT|KIT|.
S05|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|9001
S05|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|.
S06|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S06|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1099
S07|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S07|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1003
S07|3|101|1003|LOT-C|B03|KIT REPLACEMENT|KIT|1002
S09|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|.
S09|2|101|1001|LOT-B|B02|KIT REPLACEMENT|KIT|1002
S10|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S11|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S11|2|101|1002|LOT-T1|BT1|KIT REPLACEMENT|KIT|.
S11|3|202|2001|LOT-X|B91|CYCLE 1 DAY 1|KIT|1002
S11|4|202|1002|LOT-T2|BT2|KIT REPLACEMENT|KIT|.
S12|1|101|1001|LOT-A|B01|discontinue|KIT|1002
S12|2|101|1002|LOT-B|B02|kit replacement|KIT|.
S14|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S14|2|101|1002|LOT-B1|B02|KIT REPLACEMENT|KIT|1003
S14|3|101|1002|LOT-B2|B03|KIT REPLACEMENT|KIT|1004
S14|4|101|1003|LOT-T3|BT3|KIT REPLACEMENT|KIT|.
S14|5|101|1004|LOT-T4|BT4|KIT REPLACEMENT|KIT|.
S17|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S17|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1003
S17|3|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1003
S17|4|101|1003|LOT-C|B03|KIT REPLACEMENT|KIT|.
;
run;

*--------------------------------------------------------------------*;
*  What every visit-level row must resolve to                        *;
*  case|scn_num|visit -> kit | lot | batch | status | probes         *;
*--------------------------------------------------------------------*;
data expect;
     length case $3 vis $20 exp_lot $10 exp_batch $10 exp_status $10;
     infile datalines dlm = '|' dsd truncover;
     input case $ scn_num vis $ exp_kit exp_lot $ exp_batch $ exp_status $ exp_probes;
datalines;
S01|101|CYCLE 1 DAY 1|1001|LOT-A|B01|RESOLVED|0
S02|101|CYCLE 1 DAY 1|1002|LOT-B|B02|RESOLVED|1
S03|101|CYCLE 1 DAY 1|1004|LOT-D|B04|RESOLVED|3
S05|101|CYCLE 1 DAY 1|1001|LOT-A|B01|DANGLING|1
S06|101|CYCLE 1 DAY 1|1002|LOT-B|B02|DANGLING|2
S07|101|CYCLE 1 DAY 1|1003|LOT-C|B03|UNRESOLVED|100
S09|101|CYCLE 1 DAY 1|1001|LOT-A|B01|RESOLVED|0
S10|101|CYCLE 1 DAY 1|1001|LOT-A|B01|DANGLING|1
S11|101|CYCLE 1 DAY 1|1002|LOT-T1|BT1|RESOLVED|1
S11|202|CYCLE 1 DAY 1|1002|LOT-T2|BT2|RESOLVED|1
S12|101|END OF TREATMENT|1002|LOT-B|B02|RESOLVED|1
S17|101|CYCLE 1 DAY 1|1003|LOT-C|B03|RESOLVED|2
;
run;

*--------------------------------------------------------------------*;
*  S15: a volume case, generated rather than typed.                  *;
*  Every subject has four visits and every visit its own kit block:  *;
*  the visit row points at k0+1, k0+1 .. k0+3 are the replacement    *;
*  rows, and k0+3 is terminal, so the row makes &vol_links probes.   *;
*--------------------------------------------------------------------*;
%if &vol_subjects > 0 %then %do;

data vol_kit;
     length case $3 vis_type $20 kit_tyds $8 lot_num $10 btch_num $10;
     case = "S15"; kit_tyds = "KIT";
     lot_num = "LOT-V"; btch_num = "B-V";
     do s = 1 to &vol_subjects;
          scn_num = 900000 + s;
          do v = 1 to &vol_visits;
               k0 = 1000000 + s * 1000 + v * 20;
               vis_type = "CYCLE 1 DAY " || strip(put(v, best.));
               kit_num = k0; kitnumrp = k0 + 1; rowid = 1;
               output;
               do j = 1 to &vol_links;
                    vis_type = "KIT REPLACEMENT";
                    kit_num  = k0 + j;
                    if j < &vol_links then kitnumrp = k0 + j + 1;
                    else kitnumrp = .;
                    rowid = 1 + j;
                    output;
               end;
          end;
     end;
     drop s v j k0;
run;

data vol_expect;
     length case $3 vis $20 exp_lot $10 exp_batch $10 exp_status $10;
     case = "S15"; exp_lot = "LOT-V"; exp_batch = "B-V";
     exp_status = "RESOLVED"; exp_probes = &vol_links;
     do s = 1 to &vol_subjects;
          scn_num = 900000 + s;
          do v = 1 to &vol_visits;
               vis = "CYCLE 1 DAY " || strip(put(v, best.));
               exp_kit = 1000000 + s * 1000 + v * 20 + &vol_links;
               output;
          end;
     end;
     drop s v;
run;

data raw_kit; set raw_kit vol_kit; run;
data expect;  set expect  vol_expect; run;

%end;

*====================================================================*;
*  The step under test                                               *;
*  The same statements as the program. The only differences are the  *;
*  input data set of the split step, and two lines marked            *;
*  "verifier" that count the probes a row makes.                     *;
*====================================================================*;
%macro run_case(c);

/* 1. split the IRT feed */
data irt_base irt_rp;
     set raw_kit(where = (case = "&c"));
     vis_type = upcase(vis_type);
     if vis_type = "DISCONTINUE" then vis_type = "END OF TREATMENT";
     keep scn_num kit_tyds kit_num lot_num vis_type btch_num kitnumrp;
     if vis_type = "KIT REPLACEMENT" then output irt_rp;
     else if not missing(kit_tyds) then output irt_base;
run;

proc sql noprint;
     select count(*) into :n_pre  from irt_rp;
quit;

/* 2. one row per kit, with the payload carried in the BY list */
proc sort data = irt_rp nodupkey;
     by scn_num kit_num kitnumrp lot_num btch_num;
run;

/* the same deduplication on the key alone, for comparison */
data irt_rp_narrow; set irt_rp; run;
proc sort data = irt_rp_narrow nodupkey;
     by scn_num kit_num;
run;

proc sql noprint;
     select count(*) into :n_wide   from irt_rp;
     select count(*) into :n_narrow from irt_rp_narrow;
quit;

data _cnt;
     length case $3;
     case = "&c";
     n_pre = &n_pre; n_wide = &n_wide; n_narrow = &n_narrow;
run;
proc append base = counts data = _cnt; run;

/* 3. walk the replacement chain to its terminal kit */
data irt_chase;
     if _n_ = 1 then do;
          declare hash h(dataset: "irt_rp", duplicate: "error");
          h.definekey("scn_num","kit_num");
          h.definedata("kitnumrp","lot_num","btch_num");
          h.definedone();
     end;
     set irt_base;

     length chain_status $10;
     prev_kit = kit_num;
     chain_status = '';
     probes = 0;                                         /* verifier */

     do i = 1 to 100 while (not missing(kitnumrp));
          kit_num = kitnumrp;
          probes + 1;                                    /* verifier */
          rc = h.find();
          if rc ne 0 then do;
               chain_status = 'DANGLING';
               kit_num = prev_kit;
               leave;
          end;
          prev_kit = kit_num;
     end;

     if chain_status = '' then
        chain_status = ifc(missing(kitnumrp), 'RESOLVED', 'UNRESOLVED');

     if chain_status ne 'RESOLVED' then
        put "WARNING: kit chain " chain_status= scn_num= vis_type= kit_tyds= kit_num=;

     drop i rc prev_kit;
run;

/* 4. collapse to one reference list per subject and visit */
proc sort data = irt_chase;
     by scn_num vis_type kit_tyds kit_num;
run;

data irt_claps;
     set irt_chase;
     by scn_num vis_type kit_tyds kit_num;
     length refid $200;
     retain refid;
     if first.vis_type then refid = strip(put(kit_num, best.));
     else refid = strip(refid) || ', ' || strip(put(kit_num, best.));
     if last.vis_type;
run;

data _ap;
     length case $3;
     set irt_claps;
     case = "&c";
run;
proc append base = actual data = _ap; run;

%mend run_case;

%macro run_all;
     %local i c;
     %do i = 1 %to %sysfunc(countw(&cases));
          %let c = %sysfunc(scan(&cases, &i));
          %run_case(&c)
     %end;
%mend run_all;
%run_all

*====================================================================*;
*  S14 is not in the loop above: its load is refused. What is        *;
*  checked here is the precondition -- that the conflict reaches the *;
*  load under the key-and-payload BY list, and does not under the    *;
*  key-only list.                                                    *;
*====================================================================*;
data s14_base s14_rp;
     set raw_kit(where = (case = "S14"));
     vis_type = upcase(vis_type);
     if vis_type = "DISCONTINUE" then vis_type = "END OF TREATMENT";
     keep scn_num kit_tyds kit_num lot_num vis_type btch_num kitnumrp;
     if vis_type = "KIT REPLACEMENT" then output s14_rp;
     else if not missing(kit_tyds) then output s14_base;
run;

data s14_keys; set s14_rp; run;
proc sort data = s14_keys nodupkey;
     by scn_num kit_num kitnumrp lot_num btch_num;
run;

data s14_keys_narrow; set s14_rp; run;
proc sort data = s14_keys_narrow nodupkey;
     by scn_num kit_num;
run;

proc sql noprint;
     select count(*) into :s14_pre    from s14_rp;
     select count(*) into :s14_wide   from s14_keys;
     select count(*) into :s14_narrow from s14_keys_narrow;
quit;

data _cnt;
     length case $3;
     case = "S14";
     n_pre = &s14_pre; n_wide = &s14_wide; n_narrow = &s14_narrow;
run;
proc append base = counts data = _cnt; run;

%macro chk(desc, exp, act);
     data _chk;
          length check $64 expected $40 actual $40 verdict $7;
          check    = "&desc";
          expected = "&exp";
          actual   = "&act";
          verdict  = ifc("&exp" = "&act", "ok", "FAIL");
     run;
     proc append base = checks data = _chk; run;
%mend chk;

*====================================================================*;
*  1. the collapsed result against the expected result               *;
*====================================================================*;
proc sort data = actual; by case scn_num vis_type; run;
proc sort data = expect; by case scn_num vis; run;

data cmp;
     merge expect(in = e) actual(in = a rename = (vis_type = vis));
     by case scn_num vis;
     length verdict $10 diff $40;
     diff = "";
     if      not e then diff = "unexpected row";
     else if not a then diff = "no row produced";
     else do;
          if kit_num      ne exp_kit    then diff = catx(" ", diff, "kit");
          if lot_num      ne exp_lot    then diff = catx(" ", diff, "lot");
          if btch_num     ne exp_batch  then diff = catx(" ", diff, "batch");
          if chain_status ne exp_status then diff = catx(" ", diff, "status");
          if probes       ne exp_probes then diff = catx(" ", diff, "probes");
     end;
     if missing(diff) then verdict = "ok"; else verdict = "FAIL";
run;

proc sql noprint;
     select count(*) into :n_row from cmp;
     select count(*) into :n_mis from cmp where verdict = "FAIL";
quit;

data _chk;
     length check $64 expected $40 actual $40 verdict $7;
     check    = "every visit row resolves to the expected kit lot and batch";
     expected = "no mismatch";
     actual   = "&n_mis of &n_row";
     verdict  = ifc(&n_mis = 0, "ok", "FAIL");
run;
proc append base = checks data = _chk; run;

*====================================================================*;
*  2. what the BY list of the deduplication decides                  *;
*     S14: two rows disagree on the same key.                        *;
*     S17: two rows agree on the same key.                           *;
*====================================================================*;
proc sql noprint;
     select n_pre    into :s14_n  from counts where case = "S14";
     select n_narrow into :s14_nr from counts where case = "S14";
     select n_pre    into :s17_n  from counts where case = "S17";
     select n_wide   into :s17_w  from counts where case = "S17";
     select n_narrow into :s17_nr from counts where case = "S17";
quit;
%chk(S14 replacement rows entering the deduplication, 4, &s14_n)
%chk(S14 keys left by the key-and-payload BY list, 4, &s14_wide)
%chk(S14 keys the key-only BY list would leave, 3, &s14_nr)
%chk(S17 replacement rows entering the deduplication, 3, &s17_n)
%chk(S17 keys left by the key-and-payload BY list, 2, &s17_w)
%chk(S17 keys the key-only BY list would leave, 2, &s17_nr)

*====================================================================*;
*  3. F4  ECREFID describes every kit of the visit, ECLOT and        *;
*     BATCHNUM one of them. Three kits is what the collapse sees.    *;
*====================================================================*;
data f4_chase;
     length vis_type $20 kit_tyds $8 lot_num $10 btch_num $10 chain_status $10;
     scn_num = 101; vis_type = "CYCLE 1 DAY 1"; kit_tyds = "KIT";
     chain_status = "RESOLVED";
     do n = 0 to 2;
          kit_num  = 1001 + n;
          lot_num  = "LOT-" || put(n, z2.);
          btch_num = "B"   || put(n, z2.);
          output;
     end;
run;

proc sort data = f4_chase;
     by scn_num vis_type kit_tyds kit_num;
run;

data f4_claps;
     set f4_chase;
     by scn_num vis_type kit_tyds kit_num;
     length refid $200;
     retain refid;
     if first.vis_type then refid = strip(put(kit_num, best.));
     else refid = strip(refid) || ', ' || strip(put(kit_num, best.));
     if last.vis_type;
run;

data _chk;
     length check $64 expected $40 actual $40 verdict $7;
     set f4_claps;
     check    = "F4 ECREFID lists every kit of the visit";
     expected = "1001, 1002, 1003";
     actual   = refid;
     verdict  = ifc(refid = "1001, 1002, 1003", "ok", "FAIL");
     output;
     check    = "F4 ECLOT and BATCHNUM belong to the last kit in sort order";
     expected = "1003 LOT-02 B02";
     actual   = catx(" ", strip(put(kit_num, best.)), lot_num, btch_num);
     verdict  = ifc(kit_num = 1003 and lot_num = "LOT-02" and btch_num = "B02",
                    "ok", "FAIL");
     output;
     keep check expected actual verdict;
run;
proc append base = checks data = _chk; run;

*====================================================================*;
*  4. S15  the volume case                                           *;
*====================================================================*;
%if &vol_subjects > 0 %then %do;
proc sql noprint;
     select count(*) into :v_row from actual where case = "S15";
     select count(*) into :v_bad from actual
        where case = "S15" and (chain_status ne "RESOLVED" or probes ne &vol_links);
quit;
%chk(S15 visits walked, %eval(&vol_subjects * &vol_visits), &v_row)
%chk(S15 rows off the terminal kit or over the probe budget, 0, &v_bad)
%end;

*====================================================================*;
*  Report                                                            *;
*====================================================================*;
title "Kit chain check -- every visit row, and what it resolved to";
proc print data = cmp noobs;
     where case ne "S15" or verdict = "FAIL";
     var case scn_num vis exp_kit kit_num exp_lot lot_num exp_batch btch_num
         exp_status chain_status exp_probes probes verdict;
run;

title "Kit chain check -- F4 the collapsed record for a three-kit visit";
proc print data = f4_claps noobs;
     var scn_num vis_type refid kit_num lot_num btch_num;
run;

title "Kit chain check -- assertions";
proc print data = checks noobs;
     var check expected actual verdict;
run;
title;

proc sql noprint;
     select count(*) into :n_chk from checks;
     select count(*) into :n_bad from checks where verdict ne "ok";
quit;

%put NOTE: ============================================================;
%put NOTE: kit chain check: &n_chk checks, %eval(&n_chk - &n_bad) pass, &n_bad fail;
%put NOTE: visit rows compared: &n_row, mismatching: &n_mis;
%put NOTE: ============================================================;

*====================================================================*;
*  S14  the conflict, and the load that refuses it                   *;
*  EXPECTED: an ERROR line naming the duplicate key, and no          *;
*  WORK.IRT_CHASE output data set. That is the guardrail firing.     *;
*====================================================================*;
%if %upcase(&demo_conflict) = Y %then %do;
%put NOTE: ------------------------------------------------------------;
%put NOTE: S14 demo follows. The ERROR below is the expected outcome.;
%put NOTE: ------------------------------------------------------------;

data irt_base irt_rp;
     set raw_kit(where = (case = "S14"));
     vis_type = upcase(vis_type);
     if vis_type = "DISCONTINUE" then vis_type = "END OF TREATMENT";
     keep scn_num kit_tyds kit_num lot_num vis_type btch_num kitnumrp;
     if vis_type = "KIT REPLACEMENT" then output irt_rp;
     else if not missing(kit_tyds) then output irt_base;
run;

proc sort data = irt_rp nodupkey;
     by scn_num kit_num kitnumrp lot_num btch_num;
run;

data irt_chase;
     if _n_ = 1 then do;
          declare hash h(dataset: "irt_rp", duplicate: "error");
          h.definekey("scn_num","kit_num");
          h.definedata("kitnumrp","lot_num","btch_num");
          h.definedone();
     end;
     set irt_base;
     do i = 1 to 100 while (not missing(kitnumrp));
          kit_num = kitnumrp;
          rc = h.find();
          if rc ne 0 then leave;
     end;
run;

%put NOTE: S14 demo finished. No data set above is the expected result.;
%end;

%if &n_bad > 0 %then %do;
     %put ERROR: kit chain check FAILED -- &n_bad of &n_chk assertions did not hold.;
     %abort cancel;
%end;
