# Data sources for the Hereafter simulator

Every CSV in this directory is reduced from a table published by Statistics Canada (StatCan).
Nothing here is hand-typed or invented. All downloads were made on **2026-09-19**.

- Geography: Canada (national level) everywhere, except `interprovincial_flows.csv`.
- Probabilities and rates are decimals per person per year (never per 1,000).
- Dollar amounts are **2020 Canadian dollars** (Census 2021 income reference year), not inflated.
- Full-table downloads: `https://www150.statcan.gc.ca/n1/tbl/csv/<PID>-eng.zip`
  (table viewer: `https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=<PID>01`).
- Licence: Statistics Canada Open Licence (https://www.statcan.gc.ca/en/reference/licence).
  Adapted from Statistics Canada tables listed below; this does not constitute an endorsement by
  Statistics Canada of this product.

Status vocabulary

| Status | Meaning |
|---|---|
| `published` | values are straight from the table, only reshaped |
| `derived` | arithmetic on published values; the arithmetic is described |
| `approximate` | not obtained from a published table |

No file in this release is `approximate`. One file is `published`, nine are `derived`.

## Rebuilding

```
python3 data/build/fetch.py  <cache_dir>      # ~120 MB of raw zips + one small WDS JSON
python3 data/build/build_all.py <cache_dir>   # writes data/*.csv
python3 data/build/check.py                   # sanity checks (ranges, sums, row counts)
```

Raw zips are not committed. Re-running later may pick up newer reference periods for the
scripts that select "latest" (mortality, fertility, job tenure, DHEA owner rates); the others
pin their reference period in the script (overridable by a third CLI argument).

---

## 1. mortality.csv — Status: `published`

- Source: StatCan table **13-10-0114-01**, "Life expectancy and other elements of the complete life
  table, three-year estimates, Canada, all provinces except Prince Edward Island".
  https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310011401
- Reference period: **2022/2024** (three-year life table, latest available).
- Transformation: rows with GEO = Canada and Element = "Death probability between age x and x+1
  (qx)" copied as-is. Sex relabelled Males→`M`, Females→`F`, Both sexes→`both`. Age label
  "N years" → N.
- Rows: 333 = ages 0..110 x 3 sexes. Age 110 is the table's closing row "110 years and over", for
  which StatCan publishes qx = 1. Drop it if you want exactly 0..109.
- Script: `build/build_mortality.py`

## 2. first_marriage.csv — Status: `derived`

- Source: StatCan table **39-10-0057-01**, "Number of persons who married in a given year and
  marriage rate per 1,000 unmarried persons, by age group and legal marital status".
  https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3910005701
- Series used: Legal marital status prior to marriage = **Never legally married**, Indicator =
  Marriage rate (persons who married / never-legally-married population of the same age group on
  July 1, per 1,000).
- Reference period: **2019** for the level; **2002** for the male/female differential (see below).
  The table ends in 2020, but 2020 rates are about one third lower because of COVID-19
  restrictions (e.g. 27.2 vs 40.6 per 1,000 at 25-29), so 2019 was used as the latest
  representative year. StatCan flags 2019 and 2020 as preliminary and possibly underestimated.
  To use 2020: `python3 build_first_marriage.py <cache> <out> 2020`.
- Transformation:
  1. `hazard = rate / 1000`.
  2. 5-year groups expanded to single years as a step function (every age in the group gets the
     group rate). "Under 20 years" is applied to ages 15-19; "70 to 74 years" supplies age 70.
  3. `sex = both`: the 2019 "Total - Gender" rate.
  4. `sex = M` / `F`: StatCan has not published Canada-level marriage rates by gender since 2002
     (table note 8: some provinces stopped reporting gender in 2003). We carry the last published
     differential forward:
     `hazard_sex(g) = hazard_both(g, 2019) x rate_sex(g, 2002) / rate_both(g, 2002)`.
     The M/F rows therefore assume that the ratio of male (female) to overall first-marriage
     rates within each age group is unchanged since 2002.
- Caveats: legal marriage only — common-law unions are not counted, so this understates
  partnership formation (especially in Quebec). Marriages registered in
  Canada regardless of residence.
- Rows: 168 = ages 15..70 x 3.
- Script: `build/build_first_marriage.py`

## 3. divorce.csv — Status: `derived`

- Source: StatCan table **39-10-0054-01**, "Number of divorces and divorce rate per 1,000
  marriages, by duration of marriage".
  https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3910005401
- Reference period: **2019**. The table ends in 2020, but 2020 divorces fell about 25% because of
  COVID-19 court slowdowns. 2019 and 2020 are flagged preliminary/possibly underestimated by StatCan.
- What is published: for each duration d = 0 ("Under 1 year") .. 50, divorces granted in the
  reference year to couples married d years earlier, divided by the **original** size of that
  marriage cohort (table note 11). That is an unconditional density, not a hazard.
- Transformation (synthetic-cohort / period approach, the same construction as StatCan's total
  divorce rate):
  - `r_d = published rate / 1000`
  - `S_d = 1 - sum_{k<d} r_k` (share of marriages not yet divorced when reaching duration d)
  - `hazard_d = r_d / S_d`
- Cross-check: `sum_d r_d` = 0.3695 vs the published 2019 "50-year total divorce rate" of 369.4 per
  1,000 marriages (table 39-10-0051-01).
- Caveats: marriages ended by death or emigration are not removed from the denominator (neither
  does StatCan), so hazards at long durations are slightly understated. Nothing is published beyond
  50 years.
- Rows: 51 (duration 0..50).
- Script: `build/build_divorce.py`

## 4. fertility.csv — Status: `derived` (unit change and step expansion only)

- Source: StatCan table **13-10-0418-01**, "Crude birth rate, age-specific fertility rates and total
  fertility rate (live births)". https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1310041801
- Reference period: **2024**.
- Transformation: age-specific fertility rates (live births per 1,000 females, seven 5-year groups
  15-19 .. 45-49) divided by 1,000 and repeated for each single year of age in the group (step
  function). Sum of the 35 rates = 1.254, matching the published 2024 total fertility rate (1.25).
- Rows: 35 (ages 15..49).
- Script: `build/build_fertility.py`

## 5. income.csv — Status: `derived`

- Sources (Census of Population 2021, income reference year **2020**, persons aged 15+ in private
  households **with employment income**, both genders, all work activity — i.e. part-time and
  part-year workers are included, which is why p10/p25 are low):
  - A. Table **98-10-0066-01**, "Employment income groups by age and gender: Canada, provinces and
    territories, census metropolitan areas and census agglomerations with parts" — counts of
    persons per employment-income bracket and the published median, by age band.
    https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810006601
  - B. Table **98-10-0410-01**, "Employment income statistics by highest level of education and
    major field of study (summary): Canada, provinces and territories, census metropolitan areas
    and census agglomerations with parts" — published **median** employment income by CIP 2021
    primary grouping x age band (all education levels, all work activity, income year 2020).
    https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810041001
    The full zip is ~287 MB, so only the 72 cells needed were retrieved through the StatCan Web
    Data Service (`getDataFromCubePidCoordAndLatestNPeriods`, coordinates
    `1.1.<age>.1.1.1.<field>.3.0.0`); they are stored in the cache as `98100410_wds.json`.
- Only medians are published by field of study; percentiles are not published at all. Hence:
  - `field = all`: p10, p25, p75, p90 are computed from the bracket counts in A by linear
    interpolation inside the bracket containing the percentile (uniform density; the bottom bracket
    "Under $5,000 (including loss)" is treated as $0-$5,000). **p50 is the published median** from A
    (the interpolated medians are within 5% of the published ones; worst case 65+: 8,100 vs 7,750).
  - Open top bracket: where more than 10% of earners are in "$100,000 and over", p90 cannot be
    interpolated. For those cells — **p90 of `all` for ages 35-44, 45-54 and 55-64** — a Pareto tail
    is fitted to the last closed bracket:
    `alpha = ln(S(90k)/S(100k)) / ln(100/90)`, `p90 = 100000 x (S(100k)/0.10)^(1/alpha)`, where S(x)
    is the share of earners above x. These three numbers (119,700 / 132,300 / 115,700) are model
    extrapolations, not interpolations.
  - `field = <slug>`: every percentile of the `all` row for the same age band is multiplied by
    `(field median / all-fields median)`, both medians from B. This assumes each field's
    distribution has the same shape as the overall one; only its p50 is a published number
    (p50 may differ from the published field median by rounding, and by the small A-vs-B
    difference in the overall median: A is 100% administrative data, B is the 25% long-form sample).
  - Rounded to the nearest $100 (except the published `all` p50).
- Field slug ← CIP 2021 primary grouping: education ← Education; arts ← Visual and performing arts,
  and communications technologies; humanities ← Humanities; social_sciences_law ← Social and
  behavioural sciences and law; business ← Business, management and public administration;
  sciences ← Physical and life sciences and technologies; math_cs ← Mathematics, computer and
  information sciences; engineering ← Architecture, engineering, and related trades; agriculture ←
  Agriculture, natural resources and conservation; health ← Health and related fields; services ←
  Personal, protective and transportation services; all ← Total (includes people with **no**
  postsecondary credential, which matters most in the 15-24 band).
- Caveats: field rows pool every credential level (trades certificate to doctorate). 2020 was a
  pandemic year: employment income excludes CERB and other COVID benefits. The same table also
  carries 2019 incomes (set `INCOME_YEAR_MEMBER = 2` in `fetch.py`), but table A does not.
- Age bands: 15-24, 25-34, 35-44, 45-54, 55-64, 65-120 ("65 years and over").
- Rows: 72 = 12 fields x 6 age bands.
- Scripts: `build/build_income.py`, `build/binned.py`

## 6. income_bands.csv — Status: `derived`

- Source: Census 2021 table **98-10-0064-01**, "Total income groups by age and gender: Canada,
  provinces and territories, census metropolitan areas and census agglomerations with parts".
  https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810006401
- Reference period: income year **2020**; population = persons aged 15+ in private households
  **with total income** (29.2 million), both genders, all ages.
- Transformation: 20th/40th/60th/80th percentiles of individual **total** income (employment +
  investment + pensions + government transfers, before tax) interpolated linearly inside the
  published $5,000 / $10,000 brackets, rounded to $100: 19,900 / 33,100 / 50,000 / 77,000. None falls
  in an open-ended bracket. Check: interpolated median 41,100 vs published 41,200.
- `lo` is inclusive, `hi` exclusive. `low.lo = 0` (treat negative incomes as `low`); `high.hi = 1e12`.
- Caveat: 2020 total income includes pandemic benefits, which lifted the lower cut-offs relative to
  2019. Bands are for individual total income, whereas `income.csv` is employment income only.
- Script: `build/build_income_bands.py`

## 7. homeownership.csv — Status: `derived`

No StatCan table we could obtain cross-tabulates tenure by age **and** income, so the two published
margins are combined as the brief specified.

- Age margin: Census 2021 table **98-10-0231-01**, "Age of primary household maintainer by tenure:
  Canada, provinces and territories, census metropolitan areas and census agglomerations".
  https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=9810023101 — reference date May 2021.
  `age_rate = Owner / Total - Tenure` (private households; all dwelling types, condominium statuses
  and household types), for the 14 published age groups (15-19 ... 70-74, 75-84, 85+ → 85-120).
- Income margin: table **36-10-0101-01**, "Distributions of household economic accounts, number of
  households, by income quintile and by socio-demographic characteristic" (DHEA).
  https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=3610010101 — reference year **2025**.
  `income_rate(q) = Owner(q) / All households(q)`; `overall_rate = Owner / All households` = 0.6884.
  Rates: lowest 0.4087, second 0.6276, third 0.7538, fourth 0.7945, highest 0.8572.
- Combination: `owner_rate = clip(age_rate x income_rate / overall_rate, 0.02, 0.98)`. No cell
  actually hit the clip (range 0.092-0.942).
- Caveats:
  - The multiplicative form assumes age and income act independently; it is a model, not a
    published cross-tab.
  - DHEA quintiles rank households by **equivalized household disposable income**. They are mapped by
    rank to low / lower_middle / middle / upper_middle / high, but they are *not* the individual
    total-income cut-offs in `income_bands.csv`.
  - The two margins have different reference years (2021 and 2025) and different overall owner
    rates (Census 0.6647, DHEA 0.6884); the DHEA overall rate is used as the normaliser so that the
    income multipliers are internally consistent.
- Rows: 70 = 14 age groups x 5 bands.
- Script: `build/build_homeownership.py`

## 8. job_tenure.csv — Status: `derived`

- Source: StatCan table **14-10-0051-01**, "Job tenure by type of work (full- and part-time),
  annual" (Labour Force Survey). https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1410005101
- Reference period: **2025** annual average. Canada, Total - Gender, both full- and part-time.
- Transformation: `share = employed in bucket / sum of the seven buckets` within each age group
  (published unit: thousands of persons). Rounded to 4 decimals; the rounding residual (< 0.0002) is
  added to the 13-60 month bucket so that shares sum to exactly 1.
  - Age groups 15-24, 25-44, 55-64 and 65+ (→ 65-120) are published. **45-54 is obtained by
    subtraction**: count(25-54) − count(25-44).
  - One cell is suppressed by StatCan (15-24 x "241 months or more", status `x`); it is set to the
    residual Total employed − sum of the other six buckets = 0.1 thousand → share 0.0000.
  - Bounds are inclusive months as labelled by StatCan (1-3, 4-6, 7-12, 13-60, 61-120, 121-240,
    241+), except that the first bucket is written 0-3 so jobs shorter than one month have a home;
    the open top bucket uses `tenure_hi_months = 9999`.
- Caveat: tenure is elapsed time with the current employer (an incomplete spell), not completed job
  duration.
- Rows: 35 = 5 age groups x 7 buckets.
- Script: `build/build_job_tenure.py`

## 9. migration.csv — Status: `derived`

- Sources:
  - **17-10-0015-01**, "Estimates of the components of interprovincial migration, by age and
    gender, annual" — Out-migrants, GEO = Canada (sum over provinces and territories).
    https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710001501
  - **17-10-0014-01**, "Estimates of the components of international migration, by age and gender,
    annual" — component "Emigrants". https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710001401
  - **17-10-0005-01**, "Population estimates on July 1, by age and gender" (denominator).
    https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710000501
- Reference period: **2023/2024** (July 1 2023 – June 30 2024); denominator = population on
  **July 1, 2023** (the tables give age as of July 1, the start of the period). 2024/2025 exists but
  is preliminary — interprovincial counts estimated from Canada child benefit records with a
  modelled age split — so the latest final period was used (emigrants for 2023/2024 are flagged
  "updated", one step short of final). To use another period:
  `python3 build_migration.py <cache> <out> 2024/2025`.
- Transformation: `interprovincial_rate = out-migrants / population`, `emigration_rate = emigrants /
  population`, both genders, by published 5-year age group (0-4 ... 85-89; "90 years and older" →
  90-120).
- Caveats: `emigration_rate` is gross emigration to **all** countries; returning emigrants
  (53,036 vs 116,488 emigrants, all ages, 2023/2024) are not netted off and temporary emigration is not included.
  `field` is `all` on every row — see Known gaps.
- Rows: 19.
- Script: `build/build_migration.py`

## 10. interprovincial_flows.csv — Status: `derived`

- Source: StatCan table **17-10-0022-01**, "Estimates of interprovincial migrants by province or
  territory of origin and destination, annual".
  https://www150.statcan.gc.ca/t1/tbl1/en/tv.action?pid=1710002201
- Reference period: **2023/2024** (latest final estimates; preliminary 2024/2025 has zero counts
  for five small flows such as NL→YT).
- Transformation: `share = migrants(origin → destination) / sum over the 12 destinations`, all ages
  and genders. Codes: NL, PE, NS, NB, QC, ON, MB, SK, AB, BC, YT, NT, NU. The legacy combined series
  "Northwest Territories including Nunavut" is dropped.
- Rows: 156 = 13 x 12 (no origin = destination rows).
- Script: `build/build_interprovincial_flows.py`

---

## Known gaps

- **Canada → US migration by field of study is not covered.** StatCan's emigrant estimates are by
  age, gender and province only — no destination country and no field of study. `migration.csv`
  therefore has `field = all` only and its emigration rate is to all countries combined. No field
  multipliers were invented. Any "brain drain by field" effect would need a different source (e.g.
  US ACS counts of Canadian-born residents by degree field, or a published academic estimate) and
  must be labelled as such.
- **Income percentiles by field are modelled, not published.** Only field medians exist (Census
  2021). The three `all` p90 values above $100,000 rely on a Pareto-tail extrapolation, and every
  field row inherits them.
- **Incomes are 2020 dollars from a pandemic year** and are not inflation-adjusted. The Canadian
  Income Survey (tables 11-10-0239-01 / 11-10-0240-01, reference year 2024) has more recent medians
  by age but no field-of-study breakdown and no age-specific percentiles, so it was not mixed in.
- **Marriage and divorce data stop at 2020** (StatCan's vital statistics marriage/divorce databases,
  released occasionally); 2019 is used. Male/female first-marriage hazards rest on the 2002 gender
  differential. Common-law unions and their dissolution are not represented anywhere.
- **Homeownership age x income is a product of two margins**, not a cross-tabulation, and its income
  bands are household-level quintiles.
- **Life tables exclude Prince Edward Island from single-province output**, but the Canada series
  used here covers the whole country. Mortality is not broken down by income, education or field.
- **Job tenure** is a stock distribution of incomplete spells; it does not directly give job-change
  hazards.
- **Fertility** is by age of mother only (no parity, partnership status or education breakdown).

## Model assumptions (in the engine, not from a published table)

The simulator (`backend/app/sim/engine.py`) samples every transition from the tables above. The
following are rules or constants chosen by hand; they are declared at the top of `engine.py` and
are the complete list.

| Constant | Value | What it does |
|---|---|---|
| `RETIREMENT_AGE` | 65 | Everyone still working retires at the standard OAS/CPP age. |
| `LEAVE_FAMILY_HOME_AGE` | 25 | Someone living with family starts renting at this age. |
| `STUDENT_YEARS_REMAINING` | 2 | Years until a student graduates, unless the branch assumption says (`graduates_in`). |
| `RANK_PERSISTENCE` | 0.95 | Year-to-year persistence of a run's income *rank*. The rank is only ever converted to dollars through `income.csv`. |
| `JOB_CHANGE_RANK_SHOCK` | 0.35 | Extra rank noise in a job-change year. |
| income-band hysteresis | 2 years | A band change is reported only after it holds two years running. |

How the tables are applied, where that involves a judgement:

- **Job changes**: the share of the employed with under 12 months' tenure (`job_tenure.csv`) is used
  as the annual probability of starting a new job. Unemployment spells are not simulated.
- **Home purchase**: annual hazard for renters is derived from the cross-sectional ownership curve,
  `h(a) = (H(a+1) − H(a)) / (1 − H(a))`, floored at zero, with `H` interpolated between band midpoints.
- **Marriage**: the never-married rate is also applied to divorced and widowed people.
- **Widowhood**: a married run's partner is assumed the same age and the other sex's `qx` is applied.
- **Births**: age-specific fertility is applied to every run at their own age, regardless of sex or
  marital status (the published rate is per woman, unconditional on union status).
- **Migration**: rates apply only while a run lives in Canada. A run that emigrates, or whose
  branch assumption places them outside Canada (e.g. San Francisco), has no return migration, and
  the Canadian income, tenure, housing and nuptiality tables continue to apply to them.
- **Moving** resets housing to renting.
- **Personality**: `personality_effects.csv` (see `PERSONALITY_SOURCES.md`) supplies log hazard
  ratios per trait SD; each hazard is multiplied by `exp(Σ β·z·confidence)`. Rows without a
  published source carry β = 0 and have no effect.


## Model assumptions added with the outcome models (v2.1–2.2)

Declared in `backend/app/sim/outcomes.py`, `backend/app/sim/engine.py`, `backend/app/research.py`, `backend/app/scenarios.py`.
None of these is a published statistic; all are hand-set and listed here so nothing is hidden.

| Constant | Value | What it does |
|---|---|---|
| `BINS` | rare 0.02–0.10 · sometimes 0.15–0.35 · as often as not 0.40–0.60 · usually 0.70–0.90 | When no published figure is found, the LLM may only pick a verbal bin. Each simulated life draws its own probability uniformly inside the bin's range. Such events are labelled `estimated` everywhere. |
| `RELATION_MULTIPLIER` | likelier ×2 · less likely ×0.5 · prevents ×0 · requires = gate | How one possible event changes another's hazard once it has happened. The LLM names the relation; it never supplies the number. |
| `GAP_BAND` | ±0.15 | A published figure whose studied population fits the person poorly is drawn from this band around the figure rather than used as a point. The figure itself is never adjusted. |
| `TRACK_RECORD_BAND`, `MIN_TRACK_RECORD` | ±0.10, 5 | The person's own kept/ended commitments are used as a personal reference class only with at least five of them. |
| `UNANSWERED_WIDEN` | 0.08 per open question (max 2) | Stretches every range on the affected branch, and draws its line fainter by the same fraction. |
| `BAND_IN_CANADA`, `BAND_ELSEWHERE` | ±25 %, ±50 % | Each simulated life scales each life-course hazard by its own factor in this band: a national average is a loose fit for one person, looser outside Canada. |
| `USD_TO_CAD` | 1.37 | One fixed conversion for US salaries before they are placed in the Canadian income table. |
| `BASELINE_HOME_PRICE_CAD` | 700,000 | **Approximate, hand-set** national baseline. A researched local home price divided by it gives `housing_cost_ratio` (researched rents are narrative evidence only and never set a parameter); the purchase hazard is multiplied by its inverse, clipped to 0.25–2. Replace with a cited CREA / CMHC figure. |
| `SALARY_RANK_SPREAD` | 0.25 | Spread of simulated lives around a known starting salary's rank in `income.csv`. |
| `PEERS_MIN`, `PEERS_PER_ACTIVITY`, `PARENT_AGE_GAP` | 2, 6, 30 | Close same-age peers = 2 + 6 × activity; peers' weddings and first children use `first_marriage.csv` and `fertility.csv`; two parents assumed alive at the fork and 30 years older use `mortality.csv`. |

Rules rather than constants: published shares are converted to an event's window assuming a constant daily hazard
(the arithmetic is written on the evidence); a figure is accepted only if it appears literally in its quoted snippet
and parses as a percentage, "X in Y" or "X per Y"; marriage, divorce, widowhood, births and home purchase are simulated
only when the person's own log or words show they are wanted or already theirs; the life-course runs only on year
horizons and may supply at most about a quarter of a branch's visible events, giving way to the option's own events.
