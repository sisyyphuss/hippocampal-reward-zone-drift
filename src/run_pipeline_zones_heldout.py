"""
Held-out zone validation: rules out circularity in the zone-definition
process. Reward/choice zones are normally defined by pooling trial data
across ALL of a subject's sessions, then tested on PV correlations built
from those same sessions -- in principle the zone definition could be
influenced by which sessions happen to show more or less drift.

Here, for each subject: sessions are split by temporal order into two
interleaved halves (even-index / odd-index after sorting by true start
time, so both halves span the full day-distance range rather than being a
first-half/second-half split that would confound zone-definition with
session ordering). Zones are defined from ONE half only; the reward-vs-
corridor drift-rate effect is then tested on PV correlations built
EXCLUSIVELY from the OTHER half's session pairs. If the effect found on the
full pooled data was an artifact of circular fitting, it should not
replicate out-of-sample here.

Both directions are run (define-on-even/test-on-odd AND define-on-odd/
test-on-even) and reported side by side, since with modest session counts
per subject the specific split matters.
"""
from __future__ import annotations
import json
import os
import pickle
import zlib

import numpy as np
import pandas as pd

from io_nwb import load_all_sessions
from ratemaps import build_shared_grid, build_session_maps, tetrode_pooled_map
from zones import define_subject_zones, zone_pv_matrices, occupancy_matched_shuffle_test
from stats_utils import day_distance_matrix

BIN_SIZE = 4.0
SUBJECTS = ["UT14", "UT13", "UT15"]
N_SHUFFLE_PERM = 500


def trode_axis_for_subject(sessions):
    max_trode = 0
    for s in sessions:
        if len(s.units):
            max_trode = max(max_trode, int(s.units["nth_trode"].max()))
    return np.arange(1, max_trode + 1)


def build_tetrode_maps(sessions, grid, all_trodes):
    tetrode_maps, visited_list = [], []
    for s in sessions:
        occ, unit_maps, trode_ids, visited = build_session_maps(s, "_combined_maze", grid)
        tetrode_maps.append(tetrode_pooled_map(unit_maps, trode_ids, all_trodes))
        visited_list.append(visited)
    return tetrode_maps, visited_list


def run_split(subj, define_sessions, test_sessions, grid, all_trodes, label):
    """Define zones on define_sessions, test the reward-vs-corridor drift
    effect on PV correlations built exclusively from test_sessions."""
    zone_masks = define_subject_zones(define_sessions, grid)
    n_reward, n_choice, n_corridor = zone_masks.reward.sum(), zone_masks.choice.sum(), zone_masks.corridor.sum()

    tetrode_maps, visited_list = build_tetrode_maps(test_sessions, grid, all_trodes)
    true_dates = [s.true_start_dt for s in test_sessions]
    day_mat = day_distance_matrix(true_dates)

    seed = zlib.crc32(f"{subj}_{label}".encode()) % (2**31 - 1)
    shuffle_result = occupancy_matched_shuffle_test(
        tetrode_maps, visited_list, zone_masks, day_mat, n_perm=N_SHUFFLE_PERM, seed=seed
    )
    print(f"    [{subj} | {label}] zones from {len(define_sessions)} sessions "
          f"(reward={n_reward}, choice={n_choice}, corridor={n_corridor} bins), "
          f"tested on {len(test_sessions)} held-out sessions ({len(test_sessions)*(len(test_sessions)-1)//2} pairs)")
    print(f"    [{subj} | {label}] reward-vs-corridor slope diff={shuffle_result['obs_reward_diff']:.4f}, "
          f"p={shuffle_result['p_reward']:.4f}")
    return dict(
        subject=subj, label=label,
        n_define_sessions=len(define_sessions), n_test_sessions=len(test_sessions),
        n_reward_bins=int(n_reward), n_choice_bins=int(n_choice), n_corridor_bins=int(n_corridor),
        obs_reward_diff=shuffle_result["obs_reward_diff"], p_reward=shuffle_result["p_reward"],
        obs_choice_diff=shuffle_result["obs_choice_diff"], p_choice=shuffle_result["p_choice"],
        null_reward=shuffle_result["null_reward"].tolist(), null_choice=shuffle_result["null_choice"].tolist(),
        zone_masks=zone_masks,
    )


def process_subject(subj, sessions):
    sessions = sorted(sessions, key=lambda s: s.true_start_dt)
    for s in sessions:
        s.epochs["_combined_maze"] = s.epochs["dnmp"]

    grid = build_shared_grid(sessions, "_combined_maze", bin_size=BIN_SIZE)
    all_trodes = trode_axis_for_subject(sessions)

    even_sessions = sessions[0::2]  # indices 0,2,4,...
    odd_sessions = sessions[1::2]   # indices 1,3,5,...
    print(f"  [{subj}] {len(sessions)} total -> even-index half n={len(even_sessions)}, odd-index half n={len(odd_sessions)}")

    results = []
    results.append(run_split(subj, define_sessions=even_sessions, test_sessions=odd_sessions,
                              grid=grid, all_trodes=all_trodes, label="define=even_test=odd"))
    results.append(run_split(subj, define_sessions=odd_sessions, test_sessions=even_sessions,
                              grid=grid, all_trodes=all_trodes, label="define=odd_test=even"))
    return results


def main():
    os.makedirs("results/tables", exist_ok=True)
    os.makedirs("results/cache", exist_ok=True)

    print("Loading sessions...")
    sessions, skipped = load_all_sessions(subjects=SUBJECTS, force=False)
    by_subject = {}
    for s in sessions:
        by_subject.setdefault(s.subject_id, []).append(s)

    all_results = []
    for subj in SUBJECTS:
        print(f"\n=== {subj} ===")
        all_results.extend(process_subject(subj, by_subject[subj]))

    with open("results/cache/zone_heldout_results.pkl", "wb") as f:
        pickle.dump(all_results, f)

    rows = [{k: v for k, v in r.items() if k not in ("null_reward", "null_choice", "zone_masks")} for r in all_results]
    df = pd.DataFrame(rows)
    df.to_csv("results/tables/zone_heldout_summary.csv", index=False)
    print("\n" + df.to_string(index=False))

    with open("results/tables/zone_heldout_stats.json", "w") as f:
        json.dump(
            [{k: v for k, v in r.items() if k != "zone_masks"} for r in all_results],
            f, indent=2, default=str,
        )

    print("\nHeld-out validation complete. Outputs in results/")


if __name__ == "__main__":
    main()
