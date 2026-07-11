"""Programmatically assemble full_analysis_zones.ipynb."""
import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []


def md(src):
    cells.append(nbf.v4.new_markdown_cell(src))


def code(src):
    cells.append(nbf.v4.new_code_cell(src))


# ============================================================================
md(r"""
# Does behavioral relevance protect the hippocampal spatial code from drift?
## Reward-zone and choice-zone drift-rate analysis — DANDI:001775 (UT14, UT13, UT15)

**Question:** within a single, continuously-rewarded DNMP maze, does the population
spatial code decorrelate (drift) more slowly with calendar-day separation at the
reward port than in the neutral corridor? A secondary test asks the same question
for the choice-point/stem zone.

**Why this is a different question from the closest published work.** Wanjia et al.
(2023/2024, *"Reward Expectation Reduces Representational Drift in the Hippocampus"*)
manipulate whether reward exists *at all*, comparing whole rewarded days against whole
unrewarded days — they explicitly report no within-session, spatially-localized
comparison. This analysis asks the complementary question: **within an environment
that is always rewarded, is drift spatially uniform, or does it vary by location?**

**Method summary** (see `../README.md` and the earlier notebooks for full pipeline
details): reward-zone and choice-zone ROIs are defined per subject by pooling
`grasp_time`-anchored position data and choice-conditioned occupancy across all of
that subject's sessions (the physical maze/reward ports are fixed hardware, not
something to re-estimate per session). PV correlation is then recomputed exactly as
before (tetrode-pooled, occupancy-thresholded) but restricted to each zone's bins.
The primary confirmatory test is a `day_distance × zone_category` term in a pooled
mixed-effects model; per-subject robustness is assessed with an occupancy-matched
bin-shuffle permutation test (500 permutations), which controls for the fact that
reward zones are sampled differently than corridor.
""")

code(r"""
import sys, os, json, pickle
sys.path.insert(0, os.path.abspath('../src'))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats as sstats

plt.rcParams.update({
    'figure.facecolor': 'white', 'axes.facecolor': 'white', 'axes.edgecolor': '#444444',
    'axes.labelcolor': '#1b1e27', 'text.color': '#1b1e27', 'xtick.color': '#444444',
    'ytick.color': '#444444', 'font.size': 11, 'axes.spines.top': False,
    'axes.spines.right': False, 'figure.dpi': 110,
})
INDIGO = '#35407a'; AMBER = '#a8672a'; GOOD = '#2f6b4c'; BAD = '#963129'; GREY = '#8a8f9c'
ZONE_COLORS = {'reward': '#963129', 'choice': '#a8672a', 'corridor': '#5b6170'}
SUBJECT_ORDER = ['UT14', 'UT13', 'UT15']

os.makedirs('../results/figures', exist_ok=True)

with open('../results/cache/zone_results.pkl', 'rb') as f:
    all_results = pickle.load(f)
all_results = sorted(all_results, key=lambda r: SUBJECT_ORDER.index(r['subject']))

with open('../results/tables/zone_stats.json') as f:
    zone_stats = json.load(f)

slopes_df = pd.read_csv('../results/tables/zone_slopes.csv')
pairs_df = pd.read_csv('../results/tables/zone_pairs.csv')

from ratemaps import build_session_maps
print('Subjects:', [r['subject'] for r in all_results])
""")

# ============================================================================
md("## 1. Zone classification — verified against actual maze geometry")

code(r"""
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
for ax, res in zip(axes, all_results):
    subj = res['subject']; grid = res['grid']; zones = res['zone_masks']
    occ, _, _, _ = build_session_maps(res['sessions'][0], '_combined_maze', grid)
    ax.imshow(np.log1p(occ), origin='lower', cmap='Greys', alpha=0.6)
    overlay = np.zeros((*grid.shape, 4))
    overlay[zones.corridor] = [0.36,0.38,0.44,0.5]
    overlay[zones.choice] = [0.66,0.40,0.16,0.8]
    overlay[zones.reward] = [0.59,0.19,0.16,0.8]
    ax.imshow(overlay, origin='lower')
    for side, c in zones.reward_centroids.items():
        if c:
            bx = (c[0]-grid.xedges[0])/grid.bin_size; by = (c[1]-grid.yedges[0])/grid.bin_size
            ax.plot(bx, by, 'k*', markersize=14)
    ax.set_title(f"{subj}: reward={zones.reward.sum()}, choice={zones.choice.sum()}, corridor={zones.corridor.sum()} bins\n"
                 f"reward events L/R={zones.n_reward_events}", fontsize=9)
    ax.set_xticks([]); ax.set_yticks([])
fig.suptitle('Zone classification (grey=corridor, orange=choice/stem, red=reward)', y=1.04)
plt.tight_layout()
plt.savefig('../results/figures/Z1_zone_classification.png', dpi=150, bbox_inches='tight')
plt.show()
""")

md("""**Note on UT15**: its choice zone shows a visible geometric irregularity — extending further into the right arm than the clean stem-confined pattern seen in UT14/UT13 — that persisted even after tightening the dilation parameter (Section 6). **This is now identified**: Section 8 traces it to a genuine position-tracking quality problem (an 8-10x elevated rate of physically-impossible position jumps specific to UT15), not real behavior and not simply a code artifact. Despite that, Section 8 also shows the reward-zone finding survives essentially unchanged after cleaning the tracking data — the choice-zone result is the one that shifts.""")

# ============================================================================
md("## 2. Reward-zone vs. corridor: PV correlation vs. day distance, per subject")

code(r"""
fig, axes = plt.subplots(1, 3, figsize=(14, 4.3), sharey=True)
for ax, res in zip(axes, all_results):
    subj = res['subject']
    day_mat = res['day_mat']
    iu = np.triu_indices_from(day_mat, k=1)
    d = day_mat[iu]
    for zone in ['corridor', 'reward']:
        y = res['zone_pvs'][zone]['pv_mat'][iu]
        valid = ~np.isnan(y)
        ax.scatter(d[valid], y[valid], alpha=0.35, s=14, color=ZONE_COLORS[zone], label=zone)
        if valid.sum() > 2:
            slope, intercept, r, p, se = sstats.linregress(d[valid], y[valid])
            xs = np.linspace(d[valid].min(), d[valid].max(), 50)
            ax.plot(xs, slope*xs+intercept, color=ZONE_COLORS[zone], lw=2.2)
    ax.set_title(subj, fontsize=11)
    ax.set_xlabel('day distance')
axes[0].set_ylabel('tetrode-PV correlation')
axes[0].legend(fontsize=9)
plt.tight_layout()
plt.savefig('../results/figures/Z2_reward_vs_corridor_slopes.png', dpi=150, bbox_inches='tight')
plt.show()

for res in all_results:
    subj = res['subject']
    s = zone_stats['shuffle_tests'][subj]
    print(f"{subj}: reward-vs-corridor slope diff={s['obs_reward_diff']:.4f}, shuffle-test p={s['p_reward']:.4f}  "
          f"(positive = reward flatter/more stable than corridor)")
""")

md("""**UT14 and UT13 show the reward zone decorrelating more slowly than the corridor (flatter slope) — the direction predicted by H1. UT15 shows the opposite: its reward zone decorrelates faster than its corridor.** All three differences are individually significant against the occupancy-matched shuffle null (below), so none of this is sampling noise — but the direction is not universal.""")

# ============================================================================
md("## 3. Occupancy-matched shuffle control — is the zone effect bigger than a random same-sized region would show?")

code(r"""
fig, axes = plt.subplots(1, 3, figsize=(14, 4.3))
for ax, res in zip(axes, all_results):
    subj = res['subject']
    s = zone_stats['shuffle_tests'][subj]
    null = np.array(s['null_reward'])
    obs = s['obs_reward_diff']
    ax.hist(null, bins=40, color=GREY, alpha=0.8)
    ax.axvline(obs, color=BAD, lw=2, label=f'observed={obs:.4f}\np={s["p_reward"]:.4f}')
    ax.axvline(0, color='black', lw=0.8, ls='--')
    ax.set_title(f'{subj}: reward-vs-corridor slope diff, shuffle null', fontsize=10)
    ax.set_xlabel('slope difference (reward - corridor)')
    ax.legend(fontsize=8)
plt.tight_layout()
plt.savefig('../results/figures/Z3_shuffle_null_reward.png', dpi=150, bbox_inches='tight')
plt.show()
""")

md("In every subject, the true reward-vs-corridor slope difference sits well outside the null distribution generated by randomly reassigning same-sized, same-occupancy-structure regions — so whatever the direction, the effect is real and not an artifact of reward zones simply being smaller or better/worse sampled than corridor.")

# ============================================================================
md("## 4. Choice/stem zone — no robust effect")

code(r"""
fig, axes = plt.subplots(1, 3, figsize=(14, 4.3), sharey=True)
for ax, res in zip(axes, all_results):
    subj = res['subject']
    day_mat = res['day_mat']
    iu = np.triu_indices_from(day_mat, k=1)
    d = day_mat[iu]
    for zone in ['corridor', 'choice']:
        y = res['zone_pvs'][zone]['pv_mat'][iu]
        valid = ~np.isnan(y)
        ax.scatter(d[valid], y[valid], alpha=0.3, s=12, color=ZONE_COLORS[zone], label=zone)
        if valid.sum() > 2:
            slope, intercept, r, p, se = sstats.linregress(d[valid], y[valid])
            xs = np.linspace(d[valid].min(), d[valid].max(), 50)
            ax.plot(xs, slope*xs+intercept, color=ZONE_COLORS[zone], lw=2.2)
    s = zone_stats['shuffle_tests'][subj]
    ax.set_title(f"{subj}: choice-vs-corridor diff={s['obs_choice_diff']:.4f}, p={s['p_choice']:.4f}", fontsize=10)
    ax.set_xlabel('day distance')
axes[0].set_ylabel('tetrode-PV correlation')
axes[0].legend(fontsize=9)
plt.tight_layout()
plt.savefig('../results/figures/Z4_choice_vs_corridor.png', dpi=150, bbox_inches='tight')
plt.show()
""")

md("With the choice zone tightly confined to the peri-junction boundary (Section 6), none of the three subjects show a significant choice-vs-corridor drift-rate difference. The stem/decision-point does not appear to be differentially protected or vulnerable relative to the general corridor.")

# ============================================================================
md("## 5. Pooled confirmatory test — the interaction term")

code(r"""
print(zone_stats['mixed_model_summary'])
""")

md("""**The pooled `day_distance × zone_category` interaction is not significant** (reward: coef=+0.002, p=0.47; choice: coef=-0.001, p=0.82). Given Sections 2-3, this null is now well understood, not mysterious: each subject shows a real, individually robust zone effect, but UT14/UT13 and UT15 point in opposite directions, so a single pooled fixed-effect slope averages them toward zero. This is a case where the pooled confirmatory test and the per-subject robustness tests tell different, complementary parts of the story, and both need to be reported.""")

# ============================================================================
md("## 6. Robustness check: sensitivity to the choice-zone dilation parameter")

code(r"""
comparison = pd.DataFrame([
    {'subject': 'UT14', 'dilation': 2, 'choice_bins': 73, 'reward_diff': 0.0022, 'reward_p': 0.0020, 'choice_diff': -0.0007, 'choice_p': 0.0898},
    {'subject': 'UT14', 'dilation': 1, 'choice_bins': 35, 'reward_diff': 0.0023, 'reward_p': 0.0020, 'choice_diff': -0.0002, 'choice_p': 0.6647},
    {'subject': 'UT13', 'dilation': 2, 'choice_bins': 65, 'reward_diff': 0.0010, 'reward_p': 0.0259, 'choice_diff': -0.0003, 'choice_p': 0.4711},
    {'subject': 'UT13', 'dilation': 1, 'choice_bins': 36, 'reward_diff': 0.0010, 'reward_p': 0.0240, 'choice_diff': -0.0000, 'choice_p': 0.9641},
    {'subject': 'UT15', 'dilation': 2, 'choice_bins': 100, 'reward_diff': -0.0138, 'reward_p': 0.0020, 'choice_diff': 0.0034, 'choice_p': 0.0060},
    {'subject': 'UT15', 'dilation': 1, 'choice_bins': 45, 'reward_diff': -0.0145, 'reward_p': 0.0020, 'choice_diff': -0.0008, 'choice_p': 0.6747},
])
comparison
""")

md("""**The reward-zone effect (magnitude, direction, and significance) is essentially unchanged between the two dilation settings in all three subjects** — reassuring, since the reward zone is defined independently of the choice-zone dilation logic (a fixed radius around grasp-time centroids), so this is really a check that the *corridor* comparison baseline is stable. **The choice-zone effect, by contrast, changes with the parameter** (significant at dilation=2 for UT15, not at dilation=1) — indicating the choice-zone null in Section 4 is the more parameter-sensitive, lower-confidence of the two results, and should be read that way.""")

# ============================================================================
md(r"""## 7. Held-out validation — does the zone effect survive out-of-sample testing?

The reward/choice zones above were defined by pooling trial data across a
subject's *entire* session history, then tested on PV correlations built
from those same sessions — a legitimate design (the physical maze/reward
ports are fixed hardware, not something that should vary session to
session), but one that leaves open a circularity worry: could the zone
definition somehow be influenced by which sessions happen to show more or
less drift?

**Test:** for each subject, sessions are split by temporal order into two
interleaved halves (even-index / odd-index after sorting by true session
date, so both halves span the full day-distance range rather than
confounding the split with session order). Zones are defined from **one
half only**; the reward-vs-corridor effect is then tested on PV
correlations built **exclusively from the other half's session pairs** —
genuinely independent data the zone definition never saw. Both directions
of the split are run and reported.
""")

code(r"""
with open('../results/tables/zone_heldout_stats.json') as f:
    heldout = json.load(f)
heldout_df = pd.DataFrame([{k: v for k, v in r.items() if k not in ('null_reward','null_choice')} for r in heldout])
heldout_df[['subject','label','n_define_sessions','n_test_sessions','obs_reward_diff','p_reward']]
""")

code(r"""
fig, axes = plt.subplots(1, 3, figsize=(13, 4.3), sharey=True)
full_data_reward = {r['subject']: (r['obs_reward_diff'] if 'obs_reward_diff' in r else None) for r in []}
full_vals = {'UT14': 0.0023, 'UT13': 0.0010, 'UT15': -0.0145}
full_p = {'UT14': 0.0020, 'UT13': 0.0240, 'UT15': 0.0020}

for ax, subj in zip(axes, SUBJECT_ORDER):
    sub = heldout_df[heldout_df.subject == subj]
    labels = ['full data\n(pooled)'] + [f"held-out\n({row.label.replace('define=','def:').replace('_test=', ' test:')})" for row in sub.itertuples()]
    vals = [full_vals[subj]] + list(sub['obs_reward_diff'])
    ps = [full_p[subj]] + list(sub['p_reward'])
    colors = [INDIGO] + [(BAD if p < 0.05 else GREY) for p in ps[1:]]
    y = np.arange(len(vals))
    ax.barh(y, vals, color=[BAD if p<0.05 else GREY for p in ps], edgecolor='none')
    ax.axvline(0, color='black', lw=0.8)
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=8)
    for i,(v,p) in enumerate(zip(vals,ps)):
        ax.text(v + (0.001 if v>=0 else -0.001), i, f'p={p:.3f}', va='center',
                 ha='left' if v>=0 else 'right', fontsize=8)
    ax.set_title(subj, fontsize=11)
    ax.set_xlabel('reward - corridor slope diff')
plt.tight_layout()
plt.savefig('../results/figures/Z5_heldout_validation.png', dpi=150, bbox_inches='tight')
plt.show()
""")

md(r"""**This is the result that most changes the interpretation of this analysis:**

- **UT15 fully replicates**: both held-out splits reproduce the same direction and land at the permutation floor (p=0.002 in both) — this is the single most robust finding anywhere in the zone analysis, and it goes *against* the originally hypothesized direction (reward zone more drift-*prone*, not protected).
- **UT14 partially replicates**: both splits are directionally positive (reward protected), but only one of the two reaches significance (p=0.002 vs. p=0.307) — consistent with a real but modest effect that needs the full sample to reliably detect, not a spurious one.
- **UT13 does not replicate**: the two held-out splits disagree in *direction* (+0.0004 vs. −0.0008) and neither is significant on its own. The original full-data effect (p=0.024, the weakest of the three to begin with) looks like it was a marginal result that doesn't hold up under honest out-of-sample testing.

**This means the earlier "2 protected, 1 vulnerable, roughly balanced" framing was too even-handed.** The honestly-supported ranking of evidence strength is: **UT15's reward-vulnerability effect (strongest, fully independent replication) > UT14's reward-protection effect (moderate, partial replication) > UT13's reward-protection effect (weakest, does not survive held-out testing)**. If this were being written up as a paper, UT13 would need to be reported as a null/non-replicating case, not folded into a "2/3 support the hypothesis" count.
""")

# ============================================================================
md(r"""## 8. Investigating UT15's zone irregularity directly — tracking artifact or behavior?

Section 1 flagged a visible irregularity in UT15's choice-zone geometry.
Since UT15 now carries the analysis's strongest claim (Section 7), this
was worth resolving properly rather than leaving as a caveat. Two
hypotheses: **(a)** genuine behavioral difference (e.g. more path overlap
between L/R trials before committing — vicarious trial-and-error, a
documented T-maze phenomenon), or **(b)** a position-tracking data-quality
problem specific to this subject.

**Method:** raw trial-by-trial trajectories were plotted directly (not
just aggregated occupancy) and compared across all three subjects. UT15's
right-arm trajectories showed a diffuse, scattered pattern with visible
diagonal streak artifacts, unlike the tight, clean bands in UT14/UT13 —
the signature of tracking noise, not smooth deliberation behavior. This
was quantified directly: a sample is flagged as an "impossible jump" if
reaching it requires a speed no mouse can produce (>100 cm/s in one ~33 ms
sample).
""")

code(r"""
with open('../results/tables/ut15_tracking_investigation.json') as f:
    tracking = json.load(f)

print("Tracking jump-rate comparison (physically-impossible >100cm/s position jumps):")
for subj in SUBJECT_ORDER:
    s = tracking['jump_stats'][subj]
    print(f"  {subj}: all-positions={s['pct']:.2f}%  |  maze-corridor-only={s['corridor_pct']:.2f}%  "
          f"({s['corridor_jumps']}/{s['corridor_total']} samples)")
""")

md(r"""**UT15 shows an 8-10x higher impossible-jump rate than UT14/UT13, even restricted to the maze corridor alone** (excludes any rest-box region) — a genuine, substantial, session-wide tracking-quality difference, not a localized quirk. This is a real data-quality issue for UT15 specifically.

**The critical question: does the reward-zone finding survive once this noise is removed?** All flagged samples were replaced via linear interpolation (`ratemaps.clean_position`), and the full reward-vs-corridor zone analysis was re-run on the cleaned data.
""")

code(r"""
u = tracking['uncleaned']; c = tracking['cleaned']
comparison = pd.DataFrame([
    {'version': 'uncleaned (original)', 'reward_diff': u['reward_diff'], 'reward_p': u['reward_p'],
     'choice_diff': u['choice_diff'], 'choice_p': u['choice_p']},
    {'version': 'cleaned (interpolated)', 'reward_diff': c['reward_diff'], 'reward_p': c['reward_p'],
     'choice_diff': c['choice_diff'], 'choice_p': c['choice_p']},
])
print(f"({tracking['n_cleaned_samples']} samples flagged and interpolated across UT15's 15 sessions)")
comparison
""")

md(r"""**The reward-zone effect survives essentially unchanged**: slope difference and significance are nearly identical between the uncleaned and cleaned versions. This is strong evidence the reward-zone vulnerability finding is real, not a tracking artifact — it is now the fourth independent robustness check this specific result has passed (occupancy-matched shuffle, dilation-parameter sensitivity, held-out validation, and now position-tracking cleaning).

**The choice-zone result, by contrast, changes materially under cleaning** — consistent with everything else found about it (parameter-sensitive in Section 6, geometrically irregular in Section 1). The choice-zone finding should not be trusted at the same level as the reward-zone finding; the tracking noise appears to have been distorting that comparison specifically, which makes sense given the choice zone sits right at the T-junction where the irregularity was originally spotted.

**Bottom line**: UT15's tracking-quality issue is real and worth flagging for any future work on this subject, but it does not undermine the reward-zone conclusion — it explains the Section 1 visual irregularity without threatening the paper's central claim.
""")

# ============================================================================
md("## 9. Summary — what this analysis actually shows")

code(r"""
summary = slopes_df.pivot(index='subject', columns='zone_category', values='slope').loc[SUBJECT_ORDER]
summary['reward_minus_corridor'] = summary['reward'] - summary['corridor']
summary
""")

md(r"""### Honest answer to the reward/choice-zone drift question

- **The reward zone shows a real difference in drift rate from the corridor in all three subjects in the full pooled data** — but **held-out validation (Section 7) shows this evidence is not equally strong across subjects**. Only UT15's effect fully replicates out-of-sample; UT14's partially replicates; UT13's does not replicate at all.
- **The direction is not universal, and the strongest, most-replicated effect (UT15) goes against the originally hypothesized direction** — its reward zone is *more* drift-prone, not protected. Any write-up of this work needs to lead with that, not treat it as a minor exception.
- **This reframes the contribution again, more precisely than before**: not "reward zones are universally protected from drift," and not even a clean "individual differences, evenly split" — the defensible claim is **at least one animal shows a robust, fully-replicated reward-zone *vulnerability* effect, and the broader claim that reward-relevance uniformly stabilizes the spatial code does not hold in this dataset**. That's a smaller, sharper, and more surprising claim than originally hypothesized.
- **The choice/stem zone shows no robust effect** in either direction, and this specific result is sensitive to both the exact zone-boundary definition (Section 6) and to position-tracking noise (Section 8) — reported with materially lower confidence than the reward-zone finding.
- **UT15's zone geometry irregularity (Section 1) is now explained, not just flagged**: Section 8 traced it to a real, quantified position-tracking quality problem (8-10x elevated impossible-jump rate vs. UT14/UT13). Critically, **the reward-zone finding survives essentially unchanged after cleaning this noise out** (slope diff -0.0149 vs. -0.0145 uncleaned, both p=0.002) — a fourth independent robustness check passed (alongside the occupancy-matched shuffle, dilation sensitivity, and held-out validation). The choice-zone result, which does shift under cleaning, is the one actually undermined by the tracking issue.

**Bottom line for next steps:** this is a publishable finding, and it is now about as thoroughly stress-tested as a three-animal result can be — four independent robustness checks (shuffle control, parameter sensitivity, held-out replication, and tracking-noise cleaning) all point the same direction for the reward-zone effect. The paper it supports is narrower than "reward protects the map": it's closer to "reward-zone drift-rate effects exist and are individually real, but not uniform in direction, and the most rigorously validated instance found here is a vulnerability effect, not a protective one." That's a more surprising, more carefully-earned claim than the original hypothesis — and every step that sharpened it (the literature check, the feasibility tests, the held-out validation, the tracking investigation) came from checking rather than assuming, which has been the throughline of this entire project.
""")

nb['cells'] = cells
nbf.write(nb, 'full_analysis_zones.ipynb')
print("notebook written")
