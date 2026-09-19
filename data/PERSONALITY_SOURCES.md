# Personality effects: sources, quotes, conversions

Companion to `personality_effects.csv`. Compiled 2026-09-19. Every non-zero beta below was read
out of a document that was actually opened (full text or PDF), not recalled. Where a source could
not be opened, the row is `unsourced` with beta 0, even when the literature clearly has an answer
(see "Unsourced" and "Considered but not used").

Model convention: `hazard_i = baseline_hazard * exp(sum_t beta_t * z_t)`, z = trait z-score.
`income_rank` is not a hazard: beta is the shift in income normal-score per trait SD.

Counts: 15 `published`, 15 `derived`, 10 `unsourced` (40 rows).

## Summary of non-zero rows

| hazard | metric behind beta | O | C | E | A | N | source | status |
|---|---|---|---|---|---|---|---|---|
| mortality | ln(hazard ratio per SD), Cox, 5 traits mutually adjusted | -0.0101 | -0.1278 | -0.0513 | 0.0198 | 0.0296 | Jokela2013 | published |
| divorce | ln(odds ratio per SD), logistic, 5 traits mutually adjusted | 0.22 | 0.02 | 0.02 | -0.01 | 0.15 | SolomonJackson2014 | published |
| migration | ln(odds ratio per SD), logistic, between-US-states move | 0.2546 | 0.0296 | 0.0100 | -0.1278 | -0.0726 | Jokela2009 | published |
| marriage | ln(HR) converted from lifetime OR per SD (formula M1) | -0.0939 | 0.0200 | 0.0997 | 0.0102 | -0.0179 | Jokela2011 | derived |
| fertility | ln(rate ratio) converted from children-per-SD (formula F1) | -0.0791 | -0.0243 | 0.0469 | 0.0276 | -0.0202 | Jokela2011 | derived |
| income_rank | partial correlation used as standardized shift (formula I1) | 0.0165 | 0.0253 | 0.0209 | -0.0353 | -0.0330 | Alderotti2021 | derived |

"published" here means the paper reports the per-SD HR / OR / logit coefficient directly; the only
arithmetic applied is the natural log. Statistical significance is a separate question; see the
"not significant" list under Caveats before using every row at face value.

---

## Jokela2013 (mortality) -- published

Jokela M, Batty GD, Nyberg ST, Virtanen M, Nabi H, Singh-Manoux A, Kivimaki M (2013). Personality
and all-cause mortality: individual-participant meta-analysis of 3,947 deaths in 76,150 adults.
*American Journal of Epidemiology* 178(5):667-675. doi:10.1093/aje/kwt170.
Opened: PMC full text https://pmc.ncbi.nlm.nih.gov/articles/PMC3755650/ and its Figure 1 image.

- Scaling (Methods): "Hazard ratios were calculated for both continuously coded standardized
  personality scores (mean = 0; standard deviation, 1)".
- Figure 1 caption: "Hazard ratios associated with a 1-standard deviation increment in personality
  trait score for mutually adjusted personality traits, additionally adjusted for sex, age, and
  ethnicity/nationality. The overall estimates are based on random-effects meta-analysis."
- Figure 1, pooled "Subtotal" rows (HR, 95% CI), read from the figure:
  Extraversion 0.95 (0.89, 1.01); Neuroticism 1.03 (0.98, 1.09); Agreeableness 1.02 (0.96, 1.09);
  Conscientiousness 0.88 (0.82, 0.94); Openness to Experience 0.99 (0.93, 1.06).
- Text confirmation (Discussion): "a hazard ratio of 0.88 (95% CI: 0.82, 0.94) per 1-standard
  deviation increment in conscientiousness"; and for openness "the pooled estimate suggested no
  association (HR = 0.99, 95% CI: 0.93, 1.06)".
- beta = ln(HR): O ln 0.99 = -0.0101; C ln 0.88 = -0.1278; E ln 0.95 = -0.0513; A ln 1.02 = 0.0198;
  N ln 1.03 = 0.0296.
- Only conscientiousness has a CI excluding 1. The authors' own conclusion is that C is the only
  trait related to mortality across populations. The paper also notes its C estimate is "only about
  one-half to one-third of the previously estimated effect magnitudes" from earlier
  literature-based meta-analyses, so this is the conservative choice.
- Sample: 7 cohorts (US, UK, Germany, Australia), mean baseline age 50.9, mean follow-up 5.9 years.

## SolomonJackson2014 (divorce) -- published

Solomon BC, Jackson JJ (2014). Why do personality traits predict divorce? Multiple pathways through
satisfaction. *Journal of Personality and Social Psychology* 106(6):978-996. doi:10.1037/a0036190.
Opened: full-text PDF https://gwern.net/doc/psychology/personality/2014-solomon.pdf

- Table 1 "Personality Traits Predicting Relationship Dissolution" (p. 984), Model 2, columns
  b / SE / z / Odds ratio:
  Extraversion 0.02 / 0.05 / 0.34 / 1.02; Agreeableness -0.01 / 0.06 / -0.15 / 0.99;
  Conscientiousness 0.02 / 0.05 / 0.48 / 1.02; Neuroticism 0.15* / 0.05 / 2.94 / 1.16;
  Openness 0.22* / 0.05 / 4.13 / 1.24.
- Scaling (Results, same page as Table 1, p. 984): "All continuous variables were standardized for ease of interpretation with the
  exceptions of age, de facto relationships, and marriages." So b is the log odds ratio per SD and
  is used as beta with no conversion.
- Model 2 enters all five traits simultaneously plus sex, relationship duration, religion, number
  of de facto relationships, marriages, children, resident children, employment, income, education.
  Model 1 (each trait alone, "tested in separate analyses") gives larger values: A -0.09, C -0.13,
  N 0.31, O 0.30, E 0.03. Model 2 was chosen because the simulator applies all five traits jointly.
- Metric caveats: log odds ratio, not log hazard ratio. Outcome is separation or divorce between
  HILDA Waves 1 and 5 ("N = 764; approximately 11%") among 8,206 married and de facto partners in
  Australia. With an 11% cumulative incidence the OR overstates the HR only slightly.
- Only N and O are significant in Model 2.

## Jokela2009 (migration) -- published

Jokela M (2009). Personality predicts migration within and between U.S. states. *Journal of
Research in Personality* 43(1):79-83. doi:10.1016/j.jrp.2008.09.005.
Opened: author PDF (in-press layout) https://blogs.helsinki.fi/mmjokela/files/2009/03/jokela_personality_migration_jrp.pdf

- Scaling (section 2.8): "odds ratios were calculated for standardized personality scales
  (Means = 0, SD = 1)". Table 2 footnote: "Standardized odds ratios."
- O and A: Table 2, "Model 2: Between-states migration", Step 2 (adjusted for each other and for
  gender, age, race, employment, parenthood, marital status, education, neighborhood
  satisfaction), OR (SE): Openness 1.29*** (0.10); Agreeableness 0.88* (0.06). n = 3760.
  beta = ln 1.29 = 0.2546; ln 0.88 = -0.1278.
- E, N, C: not retained in Table 2 ("Neuroticism and conscientiousness did not predict migration,
  so they were omitted from the models"). The only per-SD estimates are the single-trait models in
  section 3.2: "between-states migration was predicted by openness (OR = 1.19, SE = 0.08,
  p = 0.007), but not by extraversion (OR = 1.01, SE = 0.06, p = 0.82), agreeableness (OR = 0.95,
  SE = 0.05, p = 0.34), neuroticism (OR = 0.93, SE = 0.06, p = 0.19) or conscientiousness
  (OR = 1.03, SE = 0.06, p = 0.59)."
  beta = ln 1.01 = 0.0100 (E); ln 0.93 = -0.0726 (N); ln 1.03 = 0.0296 (C). All three are
  non-significant and come from a different (single-trait) specification than the O and A rows.
- Metric caveats: log odds ratio over a 7-11 year follow-up (MIDUS, US adults aged 20-75 at
  baseline); "359 (9.2%) participants had migrated from their baseline state to another state", so
  OR is close to HR. "Migration" here means an interstate move. For within-state moves the same
  table gives (Model 1, Step 2) O 1.09, A 0.91*, E 1.25***, if a local-move hazard is ever needed.

## Jokela2011 (marriage and fertility) -- derived

Jokela M, Alvergne A, Pollet TV, Lummaa V (2011). Reproductive behavior and personality traits of
the Five Factor Model. *European Journal of Personality* 25(6):487-500. doi:10.1002/per.822.
Opened: author PDF https://blogs.helsinki.fi/mmjokela/files/2012/05/jokela_personality_reproduction_EJP.pdf

Sample: 15,729 US adults (Wisconsin Longitudinal Study graduates and siblings, MIDUS), mean age 53.
Statistical analysis section: "the five personality traits were always mutually adjusted";
"Personality scales ... were all standardized (M = 0, SD = 1) within the samples".

### Marriage (formula M1)

- Table 2 "Predicting first marriage by personality traits", block "Probability of first
  marriage", column "All" (logistic regression, odds ratio (SE), n = 15 729):
  Extraversion 1.35 (0.05); Neuroticism 0.95 (0.03); Agreeableness 1.03 (0.04);
  Conscientiousness 1.06 (0.04); Openness to experience 0.77 (0.03).
- These are odds ratios for EVER marrying, an outcome that about 93% of the sample experienced, so
  ln(OR) would badly overstate an annual hazard multiplier. Converted to a hazard ratio under
  proportional hazards:

  **M1:** P0 = baseline share ever married; odds1 = OR * P0/(1-P0); P1 = odds1/(1+odds1);
  HR = ln(1-P1) / ln(1-P0); beta = ln(HR).

  P0 = 14,665 / 15,729 = 0.93235 (n of the "Age at first marriage" model over n of the
  probability model in the same table; the paper does not print the share directly, so this is
  inferred). odds0 = 13.783.

  | trait | OR | P1 | HR | beta |
  |---|---|---|---|---|
  | O | 0.77 | 0.91389 | 0.9104 | -0.0939 |
  | C | 1.06 | 0.93594 | 1.0202 | 0.0200 |
  | E | 1.35 | 0.94900 | 1.1049 | 0.0997 |
  | A | 1.03 | 0.93419 | 1.0102 | 0.0102 |
  | N | 0.95 | 0.92905 | 0.9823 | -0.0179 |

  Sensitivity: with P0 = 0.90 the E beta is 0.112 and O is -0.106; with P0 = 0.95, 0.092 and -0.086.
- Only E and O are significant (p < .001) in the "All" column. Significant sex differences exist
  (E: men 1.53, women 1.22; A: women 1.10*, men 0.95; N: men 0.90*).
- Direction is corroborated by the same table's age-at-first-marriage block (E -0.35 years per SD,
  O +0.39 years per SD).
- Caveat: personality was measured at about age 53, after nearly all marriages, so reverse
  causation (marriage changing personality) cannot be excluded.

### Fertility (formula F1)

- Table 4 "Predicting the number of children by personality traits", Model A (adjusted for sex,
  age, study sample; traits mutually adjusted), "All (n = 15 729)", linear regression coefficient
  (SE) per trait SD in number of children:
  Extraversion 0.12 (0.01); Neuroticism -0.05 (0.01); Agreeableness 0.07 (0.01);
  Conscientiousness -0.06 (0.01); Openness to Experience -0.19 (0.01). All p < .001.
- The paper notes the linear model "produced essentially the same results as Poisson regression".
- If every annual birth hazard is multiplied by exp(beta), expected completed family size is
  multiplied by approximately exp(beta). Hence:

  **F1:** beta = ln((M + b) / M), M = pooled mean number of children, b = Table 4 coefficient.

  M from Table 1 means and n: (6763*2.66 + 3974*2.52 + 4992*2.26) / 15729 = 2.4977.

  | trait | b | (M+b)/M | beta |
  |---|---|---|---|
  | O | -0.19 | 0.9239 | -0.0791 |
  | C | -0.06 | 0.9760 | -0.0243 |
  | E | 0.12 | 1.0480 | 0.0469 |
  | A | 0.07 | 1.0280 | 0.0276 |
  | N | -0.05 | 0.9800 | -0.0202 |

- Caveats: Model A effects are total effects, partly operating through marriage timing (Model D/E
  in the same table shrink E to 0.05/0.02 and O to -0.12/-0.05). If the simulator already tilts
  the marriage hazard with the marriage row, applying the full fertility betas double-counts some
  of the E and O effect; Model E values (E 0.02, N -0.04, A 0.03, C -0.05, O -0.05) are the
  "net of timing" alternative. Effects are stronger in women (A, C, N are women-only effects).
  US cohorts whose childbearing was largely complete by the 1990s-2000s (mean age 53 at
  assessment); same reverse-causation caveat as marriage.
  The PDF's abstract text says "high openness" goes with more children, which contradicts Table 4
  and the results text ("high openness to experience had the opposite effect"); the table is used.

## Alderotti2021 (income_rank) -- derived

Alderotti G, Rapallini C, Traverso S (2021). The Big Five personality traits and earnings: a
meta-analysis. GLO Discussion Paper No. 902 [rev.]. https://hdl.handle.net/10419/237085
(PDF opened: https://www.econstor.eu/bitstream/10419/237085/1/GLO-DP-0902rev.pdf).
Published version: *Journal of Economic Psychology* 94 (2023) 102570, doi:10.1016/j.joep.2022.102570
(paywalled, NOT opened; its final numbers may differ slightly from the discussion paper).

- Table 2 "Personal earnings and the Big Five - Random effect meta-analysis" (p. 15 of the DP),
  REML estimate (SE), N effect sizes: Openness 0.0165** (0.0073), 86; Conscientiousness 0.0253***
  (0.0043), 90; Extraversion 0.0209*** (0.0043), 88; Agreeableness -0.0353*** (0.0052), 86;
  Neuroticism -0.0330*** (0.0054), 91.
- Effect size (p. 9-10): "Pearson's r partial correlation coefficient", r = t / sqrt(t^2 + df),
  i.e. the correlation between trait and earnings net of each primary study's controls. Abstract:
  63 peer-reviewed articles, 2001-2020.
- **I1:** beta = r_partial. Exact relation: standardized coefficient = r_partial *
  sqrt((1 - R2 of earnings on controls) / (1 - R2 of trait on controls)). The ratio is set to 1;
  because controls usually explain more of earnings than of the trait, this slightly overstates
  the standardized shift (true value is probably 0.8-0.9 of the listed beta).
- Caveats: heterogeneity is very high (I2 82-95%; tau larger than the mean effect). Effects are net
  of education/occupation controls in many primary studies, so they exclude the part of the
  personality effect that runs through schooling and occupational choice.

---

## Unsourced (beta = 0)

- job_change: O, C, E, A, N
- home_purchase: O, C, E, A, N

## Considered but not used

- **Zimmerman 2008** (Personnel Psychology 61(2):309-348, doi:10.1111/j.1744-6570.2008.00115.x),
  the standard meta-analysis of Big Five and turnover. Paywalled; Wiley returned 403, the ProQuest preview
  looped on redirects, and no open copy or open paper quoting its table was found (web search,
  Europe PMC full-text search). Only the
  abstract-level direction was seen (Conscientiousness and Agreeableness negatively predict actual
  turnover; Emotional Stability negatively predicts intent to quit). No coefficient was seen, so
  job_change stays unsourced. Even with the table, its values are artifact-corrected correlations
  with a binary turnover indicator and would need a base-rate-dependent conversion.
- **Niess & Zacher 2015** (PLOS ONE, doi:10.1371/journal.pone.0131115; opened via PMC4482250).
  Cox model, HILDA: Openness B = .33 (HR 1.39), others n.s. Rejected: outcome is only *upward*
  moves into managerial/professional jobs, and coefficients are per "one-unit increase" on what
  appears to be the raw 7-point scale, not per SD.
- **Roberts et al. 2007** "The Power of Personality" (Perspectives on Psychological Science
  2(4):313-345, doi:10.1111/j.1745-6916.2007.00047.x; opened via PMC4499872). Divorce aggregate:
  "the effect of Neuroticism on divorce was .17 (CIs = .12 and .22), the effect of Agreeableness
  was -.18 (CIs = -.27 and -.09), and the effect of Conscientiousness on divorce was -.13
  (CIs = -.17 and -.09)". Not used because these are r-equivalents pooled over 13 small, mostly
  unadjusted studies with unknown base rates; converting (d = r / sqrt(p(1-p)(1-r^2)), ln OR per
  SD ~ d) gives ln OR of roughly 0.27-0.40 per SD, several times larger than large-panel estimates,
  and only three traits are covered. Note the disagreement with Solomon & Jackson Model 2, where
  A and C vanish after mutual adjustment.
- **Lundberg 2010** "Personality and Marital Surplus", IZA DP 4945 (opened:
  https://docs.iza.org/dp4945.pdf; published 2012, IZA J Labor Econ 1:3,
  doi:10.1186/2193-8997-1-3, publisher site blocked). German SOEP. Text: "a one standard deviation
  increase in openness increases the divorce hazard by 12 percent for women and by 20 percent for
  men" (ln 1.12 = 0.11, ln 1.20 = 0.18, same sign and similar size as the 0.22 used). Tables are
  per raw scale point without trait SDs, so the other traits could not be converted. Marriage
  probits (ever married by 35) show O negative and C positive, consistent in sign with Jokela2011.
- **Boertien, von Scheve & Park** preprint "Can personality explain the educational gradient in
  divorce?" (opened: FU Berlin preprint PDF). Discrete-time divorce models in SOEP; trait scaling
  is non-standard (transformed scores), and results differ from HILDA (E raises divorce, OR
  1.19-1.28; C lowers it, OR 0.81-0.85; O lowers it for men). Recorded as evidence that divorce
  effects are heterogeneous across countries.
- **Ben-Shahar & Golan 2014** (personality and real-estate tenure choice) surfaced in search via
  press coverage only; paper not opened, and it concerns cross-sectional own-vs-rent, not a
  purchase hazard.
- Kern & Friedman 2008, Judge et al. 1999, Gensowski 2018, Nyhus & Pons 2005 were not opened;
  Jokela2013 and Alderotti2021 supersede them for this purpose.

## Caveats for the simulator

1. Rows whose source estimate is NOT statistically significant (CI includes no effect). Zeroing
   them is defensible: mortality O, E, A, N; divorce C, E, A; migration C, E, N; marriage C, A, N.
2. Metrics differ by row: ln HR (mortality), ln OR (divorce, migration), ln HR converted from OR
   (marriage), ln rate ratio (fertility), partial r (income_rank).
3. Single-study rows: divorce (Australia), migration (US), marriage and fertility (US cohorts born
   mid-20th century). Only mortality and income_rank are meta-analytic.
4. All estimates are observational associations, not causal effects.
5. Most sources use short Big Five inventories (adjective lists, BFI-S); measurement error
   attenuates per-SD effects relative to true-score SDs.

---

## Part 2: MBTI to NEO-PI correlations (McCrae & Costa 1989)

McCrae RR, Costa PT Jr (1989). Reinterpreting the Myers-Briggs Type Indicator from the perspective
of the five-factor model of personality. *Journal of Personality* 57(1):17-40.
doi:10.1111/j.1467-6494.1989.tb00759.x. PMID 2709300.

### What was verified, and how

**Primary source: NOT opened.** The Wiley page is paywalled, scite returned 403, and no open copy
was found by web search or Europe PMC full-text search. No table from the paper itself was seen.

**Verified from the PubMed abstract** (fetched via NCBI E-utilities, PMID 2709300): NEO-PI
self-reports and peer ratings; "Data were provided by 267 men and 201 women ages 19 to 93";
"correlational analyses showed that the four MBTI indices did measure aspects of four of the five
major dimensions of normal personality"; "no support for the view that the MBTI measures truly
dichotomous preferences or qualitatively distinct types".

**Verified from a secondary source only**: English Wikipedia, article "Myers-Briggs Type
Indicator", section "Big Five", template `Template:MBTI study` (wikitext fetched 2026-09-19),
which attributes this table to McCrae & Costa 1989:

| MBTI scale | Extraversion | Openness | Agreeableness | Conscientiousness | Neuroticism |
|---|---|---|---|---|---|
| E-I | **-0.74** | 0.03 | -0.03 | 0.08 | 0.16 |
| S-N | 0.10 | **0.72** | 0.04 | -0.15 | -0.06 |
| T-F | 0.19 | 0.02 | **0.44** | -0.15 | 0.06 |
| J-P | 0.15 | 0.30 | -0.06 | **-0.49** | 0.11 |

Sign convention per that article: correlations refer to the second letter (I, N, F, P), so
Introversion correlates -0.74 with Extraversion, Intuition +0.72 with Openness, Feeling +0.44 with
Agreeableness, Perceiving -0.49 with Conscientiousness.

### Verdict on the requested figures

- EI-Extraversion -.74, SN-Openness .72, TF-Agreeableness .44, JP-Conscientiousness -.49:
  **confirmed, but only against a secondary source** that cites the paper. All four match exactly.
- "Neuroticism essentially unmeasured": consistent with both the abstract ("four of the five") and
  the table (largest Neuroticism correlation is .16, with E-I).
- "Men's self-report sample": **could not be confirmed or refuted.** Wikipedia describes the table
  only as "based on the results from 267 men and 201 women" and does not say which subsample or
  rating source the numbers come from. Women's values and peer-rating values were not seen anywhere
  verifiable and are therefore not reported here.
- A web-search summary also offered different sex-specific figures (-.58/-.68 for E-I, .71/.65 for
  S-N). Their origin was not established (the top hit was a different study, MacDonald et al.
  1994, Psychological Reports 74:339-344); they were not verified and should not be attributed to
  McCrae & Costa.
- Worth using if an MBTI-to-Big-Five mapping is built: the off-diagonal J-P with Openness (.30) is
  non-trivial, and T-F with Extraversion (.19), E-I with Neuroticism (.16), S-N and T-F with
  Conscientiousness (-.15), J-P with Extraversion (.15) are small but non-zero. Treat all of these
  as secondary-source values until someone with journal access checks the paper's tables.

---

## How the simulator uses this file

`personality_effects.csv` carries a `significant` column (added after the research pass, from
caveat 1 above): `0` for unsourced rows and for rows whose source estimate is not statistically
significant, `1` otherwise. The engine (`backend/app/sim/tables.py`) applies **only rows with
`significant = 1`**; the rest stay in the file for the record and have no effect. Each applied
beta is further multiplied by the confidence of the person's personality estimate, so a
low-confidence estimate (an MBTI type, or an estimate from writing) barely tilts anything.
