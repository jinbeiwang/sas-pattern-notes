/*==============================================================================
  mmrm_check.sas

  Self-contained check for the note "MMRM for a longitudinal continuous
  endpoint".  Base SAS + SAS/STAT only: no study macros, no library names,
  no external input, no permanent datasets.  Every row of the note's
  scenario matrix is built here as data before it is claimed anywhere.

  Run:      sas mmrm_check.sas
  Result:   one printed row per assertion, then a pass/fail count.
  Exit:     %abort cancel when any assertion fails.

  The assertions are structural.  They settle what the model IS - how many
  covariance parameters a structure costs, what the Type 3 numerator degrees
  of freedom are, whether the baseline record stayed out of the response
  vector, whether Kenward-Roger moved the denominator degrees of freedom.
  They do not settle what the estimates are; that needs a licensed session
  and a real SAP, and the note says so.
==============================================================================*/

%let RUN_FRAGILE = 0;   /* 1 = also run the block that deliberately breaks
                           the model by leaving the baseline record in      */

/*------------------------------------------------------------------------------
  (1) FIXTURE - a de-identified ADaM BDS shape: one row per subject and visit.
      240 subjects, 3 arms, baseline plus 5 post-baseline visits at weeks
      4 / 8 / 12 / 16 / 24.  Dropout is monotone and the hazard is higher on
      placebo, which is what a symptomatic trial actually looks like.
------------------------------------------------------------------------------*/
data adlbc;
   call streaminit(20260922);
   length usubjid $8 trtp $9;
   array wk[5] _temporary_ (4 8 12 16 24);

   do subj = 1 to 240;
      usubjid = '01-' || put(subj, z3.);
      if      subj <= 80  then trtp = 'Placebo';
      else if subj <= 165 then trtp = 'Drug_Low';
      else                     trtp = 'Drug_High';

      base = 26 + 4 * rand('normal');

      avisitn = 0;                       /* the baseline record            */
      aval    = base;
      output;

      if      trtp = 'Placebo'   then slope = -0.10;
      else if trtp = 'Drug_Low'  then slope = -0.22;
      else                            slope = -0.34;

      if trtp = 'Placebo' then pdrop = 0.11;
      else                     pdrop = 0.08;

      alive = 1;
      if rand('uniform') < 0.05 then alive = 0;   /* stops before Week 4   */

      do k = 1 to 5;
         if alive = 1 then do;
            avisitn = wk[k];
            aval    = base + slope * wk[k] + 3.2 * rand('normal');
            output;
            if rand('uniform') < pdrop then alive = 0;
         end;
      end;
   end;
   drop subj slope pdrop alive k;
run;

proc sort data=adlbc;
   by usubjid avisitn;
run;

/*------------------------------------------------------------------------------
  (2) ANALYSIS DATASET.  Baseline is carried as a covariate, never as a
      response: CHG is identically zero on the baseline record, so leaving it
      in puts a zero-variance row into an unstructured matrix.
      BASE_C is centred near the grand mean for a readable intercept; the
      treatment contrast is unaffected.
------------------------------------------------------------------------------*/
data adbds;
   set adlbc;
   base_c = base - 26;
   chg    = aval - base;
   if avisitn > 0 then output;           /* (2) the whole point            */
run;

ods listing close;

/*------------------------------------------------------------------------------
  (3) THE PATTERN.  No RANDOM statement - the within-subject covariance is
      the residual covariance, which is what makes this a marginal model.
------------------------------------------------------------------------------*/
proc mixed data=adbds method=reml;
   class usubjid trtp(ref='Placebo') avisitn;
   model chg = base_c trtp avisitn trtp*avisitn / solution htype=3 ddfm=kr;
   repeated avisitn / subject=usubjid type=un r=1 rcorr=1;
   lsmeans trtp*avisitn / cl diff slice=avisitn;
   ods output CovParms = cp_un
              Tests3   = t3
              LSMeans  = lsm
              SolutionF= solf;
run;

/* (4) The same fixed effects under the three structures a SAP might fall
       back to, to count what each one costs.                              */
%macro covparm(type, out);
   proc mixed data=adbds method=reml;
      class usubjid trtp(ref='Placebo') avisitn;
      model chg = base_c trtp avisitn trtp*avisitn / ddfm=kr;
      repeated avisitn / subject=usubjid type=&type;
      ods output CovParms = &out;
   run;
%mend covparm;
%covparm(cs,     cp_cs)
%covparm(toep,   cp_toep)
%covparm(ar(1),  cp_ar1)

/* (5) The same model by ML - the note's claim is that the fixed-effect
       structure is identical and only the covariance estimates move.       */
proc mixed data=adbds method=ml;
   class usubjid trtp(ref='Placebo') avisitn;
   model chg = base_c trtp avisitn trtp*avisitn / htype=3;
   repeated avisitn / subject=usubjid type=un;
   ods output CovParms = cp_ml
              Tests3   = t3_ml;
run;

/* (6) Containment degrees of freedom, to show that KR is not cosmetic.     */
proc mixed data=adbds method=reml;
   class usubjid trtp(ref='Placebo') avisitn;
   model chg = base_c trtp avisitn trtp*avisitn / solution ddfm=contain;
   repeated avisitn / subject=usubjid type=un;
   ods output SolutionF = solf_contain;
run;

ods listing;

/*------------------------------------------------------------------------------
  (7) OBSERVED VALUES.  Counted from the data the fixture just built, so an
      assertion cannot drift away from the case it is making.
------------------------------------------------------------------------------*/
proc sql noprint;
   select count(distinct avisitn) into :K       from adbds;
   select count(*)                into :NOBS    from adbds;
   select count(distinct usubjid) into :NSUBJ   from adbds;
   select count(distinct usubjid) into :NSUBJ0  from adlbc;
   select min(avisitn)            into :MINVIS  from adbds;
   select count(*)                into :NCPUN   from cp_un;
   select count(*)                into :NCPML   from cp_ml;
   select count(*)                into :NCPCS   from cp_cs;
   select count(*)                into :NCPTOEP from cp_toep;
   select count(*)                into :NCPAR1  from cp_ar1;
   select count(*)                into :NLSM    from lsm;

   select NumDF into :DF_AVISIT from t3 where upcase(effect) = 'AVISITN';
   select NumDF into :DF_TRTP   from t3 where upcase(effect) = 'TRTP';
   select NumDF into :DF_INTER  from t3 where upcase(effect) = 'TRTP*AVISITN';
   select NumDF into :DF_BASE   from t3 where upcase(effect) = 'BASE_C';
   select NumDF into :DF_INTER_ML from t3_ml where upcase(effect) = 'TRTP*AVISITN';

   /* subjects the model can see nothing of, and subjects it sees once     */
   select count(*) into :N_NO_RESP from (
      select usubjid from adlbc group by usubjid having max(avisitn) = 0);
   select count(*) into :N_ONE_VIS from (
      select usubjid from adbds group by usubjid having count(*) = 1);
   select count(*) into :NDFDIFF from (
      select a.effect
      from solf a inner join solf_contain b
        on upcase(a.effect) = upcase(b.effect)
      where a.df > . and b.df > . and a.df ne b.df);
quit;

data _null_;
   call symputx('KR_DIFFERS',  ifc(symget('NDFDIFF')   + 0 > 0, 'YES', 'NO'));
   call symputx('HAS_NO_RESP', ifc(symget('N_NO_RESP') + 0 > 0, 'YES', 'NO'));
   call symputx('HAS_ONE_VIS', ifc(symget('N_ONE_VIS') + 0 > 0, 'YES', 'NO'));
   call symputx('HAS_DROPOUT', ifc(input(symget('NOBS'), best.)
                                   < input(symget('NSUBJ0'), best.) * 5,
                                   'YES', 'NO'));
run;

/*------------------------------------------------------------------------------
  (8) ASSERTIONS
------------------------------------------------------------------------------*/
data results;
   length id $46 want $30 got $30 ok 8;

   id = 'A1  post-baseline visits in the response vector';
   want = '5';   got = strip(symget('K'));        ok = (want = got); output;

   id = 'A2  covariance parameters, TYPE=UN';
   want = '15';  got = strip(symget('NCPUN'));    ok = (want = got); output;

   id = 'A3  covariance parameters, TYPE=CS';
   want = '2';   got = strip(symget('NCPCS'));    ok = (want = got); output;

   id = 'A4  covariance parameters, TYPE=TOEP';
   want = '9';   got = strip(symget('NCPTOEP'));  ok = (want = got); output;

   id = 'A5  covariance parameters, TYPE=AR(1)';
   want = '2';   got = strip(symget('NCPAR1'));   ok = (want = got); output;

   id = 'A6  Type 3 numerator DF, AVISITN (4, not 1)';
   want = '4';   got = strip(symget('DF_AVISIT')); ok = (want = got); output;

   id = 'A7  Type 3 numerator DF, TRTP';
   want = '2';   got = strip(symget('DF_TRTP'));   ok = (want = got); output;

   id = 'A8  Type 3 numerator DF, TRTP*AVISITN';
   want = '8';   got = strip(symget('DF_INTER'));  ok = (want = got); output;

   id = 'A9  Type 3 numerator DF, BASE_C';
   want = '1';   got = strip(symget('DF_BASE'));   ok = (want = got); output;

   id = 'A10 LS-means rows, TRTP*AVISITN';
   want = '15';  got = strip(symget('NLSM'));      ok = (want = got); output;

   id = 'A11 lowest AVISITN in the response vector (baseline out)';
   want = '4';   got = strip(symget('MINVIS'));    ok = (want = got); output;

   id = 'A12 covariance parameters, TYPE=UN under ML';
   want = '15';  got = strip(symget('NCPML'));     ok = (want = got); output;

   id = 'A13 Type 3 numerator DF, TRTP*AVISITN under ML';
   want = '8';   got = strip(symget('DF_INTER_ML')); ok = (want = got); output;

   id = 'A14 Kenward-Roger DF differs from containment';
   want = 'YES'; got = strip(symget('KR_DIFFERS')); ok = (want = got); output;

   id = 'A15 fixture contains a subject with no response at all';
   want = 'YES'; got = strip(symget('HAS_NO_RESP')); ok = (want = got); output;

   id = 'A16 fixture contains a subject seen at one visit only';
   want = 'YES'; got = strip(symget('HAS_ONE_VIS')); ok = (want = got); output;

   id = 'A17 fixture contains dropout';
   want = 'YES'; got = strip(symget('HAS_DROPOUT')); ok = (want = got); output;
run;

proc print data=results noobs label;
   var id want got ok;
   label id   = 'Assertion'
         want = 'Expected'
         got  = 'Observed'
         ok   = 'Pass';
   format ok 1.;
run;

/*------------------------------------------------------------------------------
  (9) GATE
------------------------------------------------------------------------------*/
%macro gate;
   proc sql noprint;
      select count(*) into :nfail from results where ok = 0;
      select count(*) into :ntest from results;
   quit;
   %let nfail = %sysfunc(strip(&nfail));
   %let ntest = %sysfunc(strip(&ntest));
   %put NOTE: [mmrm_check] &nfail of &ntest assertions failed.;
   %if &nfail > 0 %then %do;
      %put ERROR: [mmrm_check] one or more assertions failed - see the table above.;
      %abort cancel;
   %end;
   %else %do;
      %put NOTE: [mmrm_check] all &ntest assertions passed.;
   %end;
%mend gate;
%gate;

/*------------------------------------------------------------------------------
  (10) FRAGILE BLOCK - not an assertion.  It fits the model with the baseline
       record left in the response vector and prints what that costs, because
       the failure is the point and a scheduler should be able to skip it.
------------------------------------------------------------------------------*/
%macro fragile;
   %put NOTE: [mmrm_check] FRAGILE BLOCK: baseline record left in the response.;

   data adbds_bad;
      set adlbc;
      base_c = base - 26;
      chg    = aval - base;      /* identically 0 where AVISITN = 0 */
   run;

   ods listing close;
   proc mixed data=adbds_bad method=reml;
      class usubjid trtp(ref='Placebo') avisitn;
      model chg = base_c trtp avisitn trtp*avisitn / ddfm=kr;
      repeated avisitn / subject=usubjid type=un;
      ods output CovParms = cp_bad;
   run;
   ods listing;

   proc print data=cp_bad label;
      title2 'Baseline left in: covariance parameters on a 6x6 unstructured R';
   run;
   title2;
%mend fragile;

%macro maybe_fragile;
   %if &RUN_FRAGILE = 1 %then %do; %fragile; %end;
   %else %put NOTE: [mmrm_check] fragile block skipped (RUN_FRAGILE=0).;
%mend maybe_fragile;
%maybe_fragile;
