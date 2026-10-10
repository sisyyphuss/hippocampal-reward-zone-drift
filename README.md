# Hippocampal Representational Drift and Reward-Zone Modulation

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Data: DANDI 001775](https://img.shields.io/badge/DANDI-001775-green.svg)](https://dandiarchive.org/dandiset/001775)

This repository provides the computational analysis pipeline, executed Jupyter notebooks, and pre-computed statistical tables for the study:

> **Individual Differences in Reward-Zone Modulation of Hippocampal Representational Drift During Chronic Recording in a Spatial Working-Memory Task**  
> **Saad Yusuf**  
> *Department of Computer Science, Jamia Millia Islamia, New Delhi, India*  
> Correspondence: `syed.saad7527@gmail.com` | ORCID: `0009-0000-2333-0078`  
> Preprint available in [`preprint/`](preprint/hippocampal_reward_zone_drift_manuscript.pdf).

---

## Scientific Overview

Hippocampal place fields drift across days even in familiar, unchanging environments. While globally withholding reward has been shown to accelerate drift across whole recording sessions, whether reward-proximal locations show altered drift dynamics relative to behaviorally neutral space within a continuously rewarded environment remains untested.

This project reanalyzes chronic dorsal CA1 tetrode recordings from mice performing a delayed-non-match-to-place (DNMP) T-maze task across 15–19 sessions spanning 2–3 weeks ([DANDI:001775](https://dandiarchive.org/dandiset/001775), Kitamura Lab).

### Primary Findings
1. **Replication of Chronic Drift:** Population vector (PV) correlation computed across the full maze declined significantly with calendar-day separation in all three animals (Mantel permutation test, $r = -0.21$ to $-0.33$, all $p < .03$; Fisher's combined $p = 3.4 \times 10^{-5}$).
2. **Individual Differences in Reward Modulation:** The reward zone showed a significant drift-rate difference from the corridor in all three subjects (occupancy-matched shuffle test, all $p < .03$). However, the direction was not uniform across animals: two mice showed slower drift in the reward zone (relative stabilization), whereas one mouse showed faster drift in the reward zone (relative vulnerability).
3. **Four Independent Robustness Checks:**
   - **Occupancy-Matched Shuffle Control:** Preserving each zone's empirical size while randomizing bin assignments confirmed the effect is not driven by spatial sampling differences ($p < .03$).
   - **Parameter Sensitivity:** Zone boundaries were dilated ($1$ vs $2$ bins); reward-zone effects remained robust across settings.
   - **Held-Out Cross-Validation:** Interleaved session splits (even vs odd session halves) confirmed the vulnerability effect replicates out-of-sample ($p = .002$).
   - **Position-Tracking Artifact Cleaning:** Identified and corrected a high-velocity tracking anomaly specific to subject UT15; the biological effect survived unchanged ($p = .002$).
   - **Circadian Negative Control:** Time-of-day separation did not predict PV decorrelation after controlling for day distance ($p = .916$).

---

## Repository Structure

```
hippocampal-reward-zone-drift/
├── src/                                  # Core computational modules
│   ├── io_nwb.py                         # NWB data streaming, timestamp verification, trial extraction
│   ├── ratemaps.py                       # Spatial binning, occupancy normalization, rate maps
│   ├── pv_correlation.py                 # Tetrode-level population vector correlation matrices
│   ├── zones.py                          # Reward/choice/corridor classification & shuffle tests
│   ├── stats_utils.py                    # Mantel permutation tests, mixed-effects models, Fisher pooling
│   ├── run_pipeline_zones.py             # Primary reward/choice-zone analysis driver
│   ├── run_pipeline_zones_heldout.py     # Out-of-sample held-out validation pipeline
│   ├── investigate_ut15_tracking.py      # Quantitative position tracking artifact investigation
│   ├── run_pipeline_all.py               # Cross-subject whole-maze drift analysis driver
│   ├── run_pipeline.py                   # Single-subject (UT14) exploratory analysis pipeline
│   └── inspect_nwb.py                    # NWB structure and metadata verification utility
├── notebooks/                            # Fully executed Jupyter analysis notebooks
│   ├── full_analysis_zones.ipynb         # Primary deliverable: zone analysis, held-out validation, & QC
│   ├── full_analysis_all_animals.ipynb   # Multi-subject whole-maze drift analysis
│   └── full_analysis.ipynb               # Single-subject deep-dive (UT14)
├── results/                              # Figures, summary tables, and precomputed matrices
│   ├── figures/                          # Publication-ready figures (Figures 1-5, S1-S2, Z1-Z5, A1-A6)
│   ├── tables/                           # CSV and JSON summary statistics and pair-level data
│   └── cache/                            # Cached correlation matrices for instant reproduction
├── preprint/                             # Final camera-ready manuscript
│   └── hippocampal_reward_zone_drift_manuscript.pdf
├── requirements.txt                      # Python library dependencies
├── LICENSE                               # MIT License
└── README.md
```

---

## Detailed Description of Analysis Modules (`src/`)

Reviewers and researchers can inspect the specific analytical steps implemented in `src/`:

* **`io_nwb.py`:** Reads raw `.nwb` sessions from Dandiset 001775. Resolves absolute Unix timestamps against session metadata to prevent clock-drift artifacts, extracts trial intervals, and aligns spike trains with position tracking.
* **`ratemaps.py`:** Establishes a shared $4 \times 4\text{ cm}$ spatial grid across all sessions per animal. Computes occupancy-normalized, Gaussian-smoothed ($\sigma = 1\text{ bin}$) firing-rate maps (excluding bins with $<0.15\text{ s}$ occupancy). Includes `clean_position()` for velocity-jump interpolation.
* **`pv_correlation.py`:** Computes population vector correlations at the tetrode level (averaging units recorded per tetrode to provide a stable spatial feature representation without requiring single-unit tracking across multi-week intervals).
* **`zones.py`:** Dynamically classifies spatial bins into:
  * **Reward Zone:** $10\text{ cm}$ radius centered on median consumption position at `grasp_time`.
  * **Choice Zone:** Shared stem bins directly adjoining the choice bifurcation.
  * **Corridor:** All remaining traversed maze bins.  
  Implements the occupancy-matched bin-shuffle permutation test (500 iterations).
* **`stats_utils.py`:** Vectorized distance matrix construction, partial Mantel permutation tests (5,000 permutations), Fisher's method for cross-subject combination, and linear mixed-effects models (`statsmodels`).
* **`run_pipeline_zones.py`:** Executes the complete zone-restricted analysis across all three subjects (UT14, UT13, UT15) and generates summary statistics.
* **`run_pipeline_zones_heldout.py`:** Splits sessions into interleaved temporal halves (even/odd), defines zones on one half, and measures PV drift slopes on the unseen half to evaluate generalizability.
* **`investigate_ut15_tracking.py`:** Flags instantaneous physical tracking anomalies ($>100\text{ cm/s}$ frame displacement) and validates that the observed vulnerability in subject UT15 is not an artifact of tracking noise.

---

## Data Source & Subject Inclusion

* **Archive:** [DANDI Archive, Dandiset 001775](https://dandiarchive.org/dandiset/001775)
* **Paradigm:** Delayed-non-match-to-place (DNMP) T-maze working-memory task with dorsal CA1 tetrode arrays.
* **Included Cohort:** 
  * `UT14` (19 sessions, 171 session pairs)
  * `UT13` (15 sessions, 105 session pairs)
  * `UT15` (15 sessions, 105 session pairs)
* **Excluded Subjects:** 
  * `UT06` and `UT08` (sessions lacked absolute Unix epoch timestamps, referencing an internal clock).
  * `Hisa` (different pharmacological homecage paradigm without spike-sorted units).

---

## Reproduction & Usage

### 1. Environment Setup

```bash
git clone https://github.com/sisyyphuss/hippocampal-reward-zone-drift.git
cd hippocampal-reward-zone-drift
pip install -r requirements.txt
```

### 2. Running Pipelines

All intermediate correlation matrices and session-pair tables are cached in `results/cache/` and `results/tables/`. You can execute the analysis drivers directly:

```bash
# Run primary zone analysis
python src/run_pipeline_zones.py

# Run out-of-sample held-out cross-validation
python src/run_pipeline_zones_heldout.py

# Run tracking quality control and interpolation control
python src/investigate_ut15_tracking.py
```

### 3. Interactive Notebooks

Launch Jupyter Lab or VS Code to step through the annotated walkthroughs:
* `notebooks/full_analysis_zones.ipynb`: Reproduces all main text figures (Figures 1–5), held-out tables (Table 1), and tracking artifact analyses.
* `notebooks/full_analysis_all_animals.ipynb`: Cross-subject whole-maze drift and circadian negative control analysis.

---

## Citation

If you use this code or findings in your research, please cite:

```bibtex
@article{yusuf2026reward,
  title={Individual Differences in Reward-Zone Modulation of Hippocampal Representational Drift During Chronic Recording in a Spatial Working-Memory Task},
  author={Yusuf, Saad},
  journal={bioRxiv},
  year={2026},
  note={Preprint}
}
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
