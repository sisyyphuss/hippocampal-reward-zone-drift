# Hippocampal representational drift analysis (DANDI:001775, all animals)

This project asked three successive, increasingly-refined questions about
chronic dorsal-CA1 recordings in DANDI:001775 (Kitamura Lab / Omura et al.,
manuscript in prep), each pivot driven by what the data — and the published
literature — actually supported rather than the original hypothesis. Four
notebooks document the full trail:

- **`notebooks/full_analysis.ipynb`** — single-animal deep dive, subject
  UT14 (19 sessions). Start here for the detailed method walkthrough.
- **`notebooks/full_analysis_all_animals.ipynb`** — extends the pipeline to
  every usable subject, tests the original circadian hypothesis with full
  statistical power, and explains why it can't be answered by this dataset.
- **`notebooks/full_analysis_zones.ipynb`** — **the current primary
  deliverable**: reward-zone and choice-zone drift-rate analysis, the
  question the project pivoted to after the circadian question proved
  infeasible and two other candidate reframings turned out to be already
  published or technically unworkable on this data (see below).

## The path to the current question, briefly

1. **Original question**: does time-of-day separation between sessions
   predict decorrelation of hippocampal spatial maps? Answer: **this
   dataset cannot test it.** `session_start_time` metadata is unreliable
   (Finding 1 below), and once corrected, every usable subject's true
   recording schedule is a narrow, non-circadian daily window — except
   UT15, which has a genuine 11.3-hour span and still shows no effect
   (see `full_analysis_all_animals.ipynb`, Section 9).
2. **First reframe attempt** (reward-zone drift resistance, REM-sleep-linked
   drift, heterogeneous single-cell drift): a literature check found all of
   these substantially already published by strong groups (Ziv lab,
   Giocomo lab, and others) in 2023–2025 — see chat history / project notes
   for the specific citations found.
3. **Second reframe attempt** (theta phase-precession drift vs. rate-code
   drift across days): survived the literature check, but failed a direct
   technical feasibility test on this data — phase-precession signal was
   weak (R≈0.10–0.30 across 6 tested place cells) and the T-maze geometry
   broke the simple linearization needed to estimate it cleanly. Ripple-band
   analysis (a related candidate) was ruled out even faster: this
   dandiset's LFP is sampled at 500 Hz, too coarse for the 150–250 Hz
   ripple band, with no raw wideband fallback.
4. **Current question**: within a maze that is *always* rewarded, does the
   population code decorrelate more slowly at the reward port than in
   neutral corridor? This differs from the closest published work (Wanjia
   et al., reward-expectation-vs-drift) by testing spatial localization
   *within* a constantly-rewarded session rather than comparing rewarded vs.
   unrewarded days — a gap that paper explicitly left open.

## ⚠️ Data-quality findings — read before trusting any timestamp-based result

**1. The NWB `session_start_time` metadata field is unreliable** for
subjects UT14, UT13, and UT15 — independently confirmed for each. An
earlier survey trusted this field and concluded UT14 spanned the full
day/night cycle (02:08–21:56); true UT14 sessions actually cluster in a
14.5h–16.4h afternoon window (18 of 19 sessions).

**2. Two subjects (UT06, UT08) have no absolute clock in the file at all**
— a lab-internal relative clock (elapsed seconds since acquisition boot),
not Unix epoch. All 30 of their sessions are excluded, not converted with a
guessed offset. **Hisa** is excluded separately (different pharmacology
sub-study, no spike-sorted units). **Net: 3 of 6 subjects usable — UT14,
UT13, UT15.**

**3. This dandiset's LFP is 500 Hz** — sufficient for theta (confirmed: real
peak at 7.5–8 Hz) but insufficient for ripple-band analysis, and no raw
wideband file exists as a fallback (unlike DANDI:000059, which does have
raw 20kHz files but lacks curated spike-sorted units).

## Headline results — reward/choice zone drift analysis (current)

Zones are defined per subject by pooling `grasp_time`-anchored reward
events and choice-conditioned occupancy across all of that subject's
sessions (physical maze geometry is fixed hardware, not re-estimated per
session). PV correlation is recomputed restricted to each zone's bins,
reusing the same tetrode-pooled method as the whole-maze analysis.

| Subject | Full-data slope diff (p) | Held-out split 1 (p) | Held-out split 2 (p) | Replicates out-of-sample? |
|---|---|---|---|---|
| UT14 | +0.0023 (0.002) | +0.0028 (**0.002**) | +0.0008 (0.307) | Partial — same direction, only 1/2 splits significant |
| UT13 | +0.0010 (0.024) | +0.0004 (0.523) | **−0.0008 (0.102)** | **No — direction flips, neither split significant** |
| UT15 | −0.0145 (0.002) | −0.0110 (**0.002**) | −0.0168 (**0.002**) | **Yes — full replication, both splits significant** |

The zone-restricted analysis initially found a real, occupancy-matched-
shuffle-robust reward-vs-corridor drift-rate difference in all three
subjects, but **held-out validation** (zones defined on one temporal half
of a subject's sessions, tested on PV correlations from the other half
only — see Section 7 of `full_analysis_zones.ipynb`) changes the picture:
**UT13's effect does not survive out-of-sample testing** and should be
treated as non-replicating, not as supporting evidence. **UT15's effect —
which goes against the originally-hypothesized "reward protects" direction
— is the most rigorously validated result in the entire analysis**,
replicating cleanly in both independent halves. UT14's effect is
intermediate: consistent direction, but power-limited.

**The honest contribution is narrower than originally hoped**: not "reward
zones are universally protected from drift," and not even an even
"individual differences" split — the best-supported claim is that
reward-zone drift-rate effects are individually real but **not uniform in
direction**, and the single most rigorously validated instance found here
is a **vulnerability** effect, not a protective one. The choice/stem zone
shows no robust effect anywhere, and is additionally sensitive to the exact
zone-boundary parameter.

**UT15's zone-classification irregularity (visible in Section 1) was
investigated directly and traced to a genuine cause**: an 8-10x elevated
rate of physically-impossible position-tracking jumps (>100 cm/s, no mouse
can move that fast) specific to that subject, confirmed both visually
(raw trajectories show scattered, diagonal-streak artifacts in the right
arm that UT14/UT13 don't have) and quantitatively (3.26% vs. 0.31%/0.41%
jump rate, restricted to the maze corridor alone). **Critically, the
reward-zone finding survives essentially unchanged after cleaning this
noise out** (slope diff −0.0149 vs. −0.0145 uncleaned, both p=0.002) — a
fourth independent robustness check, alongside the shuffle control,
parameter sensitivity, and held-out validation. **The choice-zone result,
by contrast, changes materially under cleaning**, confirming it as the
less trustworthy of the two findings. Full detail in Section 8 of
`full_analysis_zones.ipynb`.

## Headline results — circadian analysis (superseded, kept for the record)

| Subject | Sessions | True time-of-day span | PV ~ day distance | PV ~ circadian distance |
|---|---|---|---|---|
| UT14 | 19 | 6.1h (+1 outlier at 20.6h) | r=-0.31, **p=0.002** | r=-0.11, p=0.48 (n.s.) |
| UT13 | 15 | 2.1h | r=-0.21, **p=0.030** | r=0.04, p=0.78 (n.s.) |
| UT15 | 15 | **11.3h** | r=-0.33, **p=0.005** | r=0.01, p=0.95 (n.s.) |
| Pooled (Fisher) | 49 sessions | — | **p=0.00003** | p=0.92 (n.s.) |

Day-to-day drift is a genuine three-animal replication and remains true
regardless of which question is asked of this dataset — it underlies both
the circadian and zone analyses.

## Project structure

```
hippocampus_circadian_analysis/
├── analysis_env/
├── data/sub-{UT14,UT06,UT08,UT13,UT15,Hisa}/   symlinks -> /home/neuroact/dandi_001775/sub-*
├── src/
│   ├── io_nwb.py                io_nwb.py — NWB loading, session_start_time correction,
│   │                             absolute-vs-relative clock check, full trials_df extraction
│   ├── ratemaps.py               shared spatial grid, occupancy & rate maps
│   ├── pv_correlation.py         tetrode-level PV correlation (primary) + ensemble check
│   ├── zones.py                  reward/choice/corridor zone classification, zone-restricted
│   │                             PV matrices, occupancy-matched shuffle control
│   ├── stats_utils.py            distance matrices, partial Mantel, Fisher combination,
│   │                             pooled mixed models (day-distance and zone-interaction)
│   ├── run_pipeline.py           single-animal (UT14) driver
│   ├── run_pipeline_all.py       all-animals circadian driver
│   ├── run_pipeline_zones.py     reward/choice-zone driver (current primary pipeline)
│   ├── run_pipeline_zones_heldout.py   held-out zone validation (define on one temporal
│   │                              half of sessions, test on the other)
│   ├── investigate_ut15_tracking.py    quantifies position-tracking jump rates across
│   │                              subjects, re-tests the reward-zone finding on cleaned
│   │                              UT15 data (uses ratemaps.clean_position)
│   └── inspect_nwb.py            structural inspection script
├── notebooks/
│   ├── full_analysis.ipynb                single-animal deep dive
│   ├── full_analysis_all_animals.ipynb    all-animals circadian analysis
│   ├── full_analysis_zones.ipynb          PRIMARY DELIVERABLE — zone drift analysis
│   │                                       + held-out validation (Section 7) + tracking-noise
│   │                                       investigation (Section 8)
│   └── build_notebook*.py                 assembly scripts for each notebook
├── results/
│   ├── figures/          01-09_*.png (UT14), A1-A6_*.png (all-animals), Z1-Z5_*.png (zones,
│   │                      Z5=held-out validation)
│   ├── tables/            session summaries, pooled_stats.json, zone_slopes.csv, zone_pairs.csv,
│   │                      zone_stats.json, zone_heldout_summary.csv, zone_heldout_stats.json,
│   │                      ut15_tracking_investigation.json
│   └── cache/              pickled intermediate data (sessions_all.pkl, zone_results.pkl,
│                            zone_heldout_results.pkl, ...)
├── requirements.txt
└── .vscode/
```

## Method notes

- **Spike sorting**: MountainSort4, per-session (no native cross-day cell
  tracking). QC: isolation ≥ 0.90, noise_overlap ≤ 0.10, ≥100 spikes/session.
- **Population vector**: tetrode-pooled multi-unit rate maps — cell identity
  isn't tracked across days, but tetrodes are fixed hardware, so a
  per-tetrode-mean-rate population vector is directly comparable across
  sessions without single-unit matching. Tetrode axis length is determined
  per subject (UT13's denser probe yields ~250-260 units/session vs.
  UT14/UT15's 76-136).
- **Zone classification** (`zones.py`): reward zone = 10cm radius around the
  median position at `grasp_time` (fallback `chewing_onset_time`), computed
  separately for L/R choice trials and pooled across a subject's sessions.
  Choice zone = stem bins visited by both L and R trials that directly
  adjoin the arm-exclusive region (1-bin morphological dilation). Corridor
  = everything else visited. Validated visually against actual maze
  occupancy (Section 1 of `full_analysis_zones.ipynb`) before trusting any
  downstream statistic.
- **Timestamp validation, two layers**: (1) every session's position
  timestamps are checked against a plausible absolute-Unix-epoch range
  before being trusted — failures (UT06, UT08) are excluded with a logged
  reason; (2) for sessions that pass, the true embedded clock replaces the
  unreliable `session_start_time` metadata field.
- **Position-tracking validation** (`ratemaps.clean_position`): any sample
  reached via a physically-impossible jump (>100 cm/s in one ~33ms frame)
  is flagged and linearly interpolated over. Not applied by default to the
  main pipeline (results were confirmed unchanged by it — see UT15
  investigation below) but available as a reusable utility, and worth
  running by default on any new subject/dataset.
- **Statistics**: per-subject inference uses partial Mantel / plain Mantel
  permutation tests (3,000-5,000 perms) or, for zone comparisons, an
  occupancy-matched bin-shuffle permutation test (500 perms) — the shuffle
  reassigns the *same* visited bins to same-sized pseudo-zones, controlling
  for the fact that reward zones are sampled differently than corridor.
  Cross-subject pooling uses Fisher's method (assumption-free) and a linear
  mixed-effects model with subject as random intercept (parametric,
  reported alongside, not in place of, the permutation results).

## How to run

```bash
cd hippocampus_circadian_analysis
source analysis_env/bin/activate

# zone analysis (current primary pipeline)
python src/run_pipeline_zones.py
python src/run_pipeline_zones_heldout.py
python src/investigate_ut15_tracking.py
cd notebooks
python build_notebook_zones.py
jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1200 full_analysis_zones.ipynb
cd ..

# circadian analysis (superseded, kept for reference)
python src/run_pipeline_all.py
cd notebooks && python build_notebook_all.py && jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1200 full_analysis_all_animals.ipynb
```

Or open any notebook directly in VS Code with the Jupyter extension and
select the `analysis_env` interpreter — all notebooks read from
`results/cache/`, so they re-execute in well under a minute unless the
cache is deleted.

## Known limitations / honest caveats

- **UT13's reward-zone effect does not survive held-out validation**
  (Section 7 of the zones notebook) — direction flips between the two
  independent halves, neither significant. Should be treated as a
  non-replicating result, not as supporting evidence, in any write-up.
- **UT15 has a real, quantified position-tracking quality problem**
  (Section 8 of the zones notebook): an 8-10x elevated rate of
  physically-impossible position jumps versus UT14/UT13, confirmed both
  visually (raw trajectories) and by direct measurement (3.26% vs.
  0.31%/0.41% jump rate in the maze corridor). This explains the Section 1
  zone-classification irregularity. **The reward-zone finding survives
  this cleaning essentially unchanged** (a fourth independent robustness
  check, alongside the shuffle control, parameter sensitivity, and
  held-out validation) — but **the choice-zone result does not**, and
  should be trusted even less than its parameter-sensitivity issue alone
  already suggested (Section 6).
- **The choice-zone result is now the weakest finding in the analysis** on
  three independent grounds: sensitive to the dilation parameter (Section
  6), sensitive to position-tracking cleaning (Section 8), and never
  significant in held-out validation for any subject (Section 7). It
  should not be reported as a positive or negative finding with any
  confidence — treat it as inconclusive.
- **n=3 subjects** for both the circadian and zone analyses — real
  three-way replication for the day-distance drift effect, but the zone
  effect's cross-subject *direction* turned out not to replicate uniformly
  even within this modest sample (held-out check above).

## Recommended next steps

1. **CRCNS hc-3** (specifically ec013/ec012/ec014/ec016's linear-track
   sessions) is the recommended dataset for a future theta phase-precession
   attempt — true 1D track geometry (avoids the T-maze linearization
   problem found here), silicon probes, and up to 33 chronic days. Its
   missing absolute timestamps (why it failed the circadian search) don't
   matter for a phase-precession question, which only needs session order.
   Not yet feasibility-tested.
2. **Consider applying `clean_position` to all subjects by default** in a
   future pipeline run — it didn't change UT15's reward-zone conclusion,
   but UT14/UT13 were never checked for their own (lower, but nonzero)
   jump rates, and a fully-cleaned pipeline would be a stronger basis for
   a final write-up than one where only the flagged subject was checked.
