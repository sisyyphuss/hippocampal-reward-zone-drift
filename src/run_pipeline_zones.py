"""
Zone-based drift analysis: does representational drift (PV correlation decline
with calendar-day distance) proceed at a different rate in the reward zone /
choice-stem zone versus the neutral corridor, within the same continuously-
rewarded DNMP maze?

Recomputes rate maps fresh from the session cache (does NOT reuse
all_subjects_full_results.pkl from run_pipeline_all.py, which predates the
trials_df field added to SessionData and would silently break on unpickling).
"""
from __future__ import annotations
import json
import os
import pickle

import numpy as np
import pandas as pd

import zlib

from io_nwb import load_all_sessions
from ratemaps import build_shared_grid, build_session_maps, tetrode_pooled_map
from zones import define_subject_zones, zone_pv_matrices, occupancy_matched_shuffle_test
from stats_utils import (
    day_distance_matrix, upper_tri, zone_interaction_mixed_model, per_subject_zone_slopes,
)

BIN_SIZE = 4.0
SUBJECTS = ["UT14", "UT13", "UT15"]
N_SHUFFLE_PERM = 500


def trode_axis_for_subject(sessions):
    max_trode = 0
    for s in sessions:
        if len(s.units):
            max_trode = max(max_trode, int(s.units["nth_trode"].max()))
    return np.arange(1, max_trode + 1)


def process_subject(subj, sessions):
    for s in sessions:
        s.epochs["_combined_maze"] = s.epochs["dnmp"]
    grid = build_shared_grid(sessions, "_combined_maze", bin_size=BIN_SIZE)
    all_trodes = trode_axis_for_subject(sessions)

    tetrode_maps, visited_list = [], []
    for s in sessions:
        occ, unit_maps, trode_ids, visited = build_session_maps(s, "_combined_maze", grid)
        tmap = tetrode_pooled_map(unit_maps, trode_ids, all_trodes)
        tetrode_maps.append(tmap)
        visited_list.append(visited)

    zone_masks = define_subject_zones(sessions, grid)
    print(f"  [{subj}] zones: reward={zone_masks.reward.sum()} bins, choice={zone_masks.choice.sum()} bins, "
          f"corridor={zone_masks.corridor.sum()} bins; reward events L/R={zone_masks.n_reward_events}")

    zone_pvs = zone_pv_matrices(tetrode_maps, visited_list, zone_masks)

    true_dates = [s.true_start_dt for s in sessions]
    day_mat = day_distance_matrix(true_dates)

    print(f"  [{subj}] running occupancy-matched shuffle test ({N_SHUFFLE_PERM} perms)...")
    seed = zlib.crc32(subj.encode()) % (2**31 - 1)
    shuffle_result = occupancy_matched_shuffle_test(tetrode_maps, visited_list, zone_masks, day_mat, n_perm=N_SHUFFLE_PERM, seed=seed)
    print(f"  [{subj}] reward-vs-corridor slope diff={shuffle_result['obs_reward_diff']:.4f}, p={shuffle_result['p_reward']:.4f} | "
          f"choice-vs-corridor slope diff={shuffle_result['obs_choice_diff']:.4f}, p={shuffle_result['p_choice']:.4f}")

    return dict(
        subject=subj, sessions=sessions, grid=grid, zone_masks=zone_masks,
        zone_pvs=zone_pvs, day_mat=day_mat, session_ids=[s.session_id for s in sessions],
        shuffle_result=shuffle_result, tetrode_maps=tetrode_maps, visited_list=visited_list,
    )


def build_long_table(all_results):
    rows = []
    for res in all_results:
        subj = res["subject"]
        day_mat = res["day_mat"]
        session_ids = res["session_ids"]
        n = len(session_ids)
        for category in ["reward", "choice", "corridor"]:
            pv_mat = res["zone_pvs"][category]["pv_mat"]
            for i in range(n):
                for j in range(i + 1, n):
                    rows.append(dict(
                        subject=subj, session_i=session_ids[i], session_j=session_ids[j],
                        zone_category=category, pv_corr=pv_mat[i, j], day_distance=day_mat[i, j],
                    ))
    return pd.DataFrame(rows)


def main():
    os.makedirs("results/cache", exist_ok=True)
    os.makedirs("results/tables", exist_ok=True)

    print("Loading sessions...")
    sessions, skipped = load_all_sessions(subjects=SUBJECTS, force=False)
    by_subject = {}
    for s in sessions:
        by_subject.setdefault(s.subject_id, []).append(s)
    for subj in by_subject:
        by_subject[subj].sort(key=lambda s: s.true_start_dt)

    all_results = []
    for subj in SUBJECTS:
        print(f"\n=== {subj} ({len(by_subject[subj])} sessions) ===")
        all_results.append(process_subject(subj, by_subject[subj]))

    with open("results/cache/zone_results.pkl", "wb") as f:
        pickle.dump(all_results, f)

    long_df = build_long_table(all_results)
    long_df.to_csv("results/tables/zone_pairs.csv", index=False)

    slopes_df = per_subject_zone_slopes(long_df)
    slopes_df.to_csv("results/tables/zone_slopes.csv", index=False)
    print("\nPer-subject, per-zone slopes (PV correlation ~ day distance):")
    print(slopes_df.to_string(index=False))

    print("\nPooled interaction mixed model (day_distance * zone_category):")
    mm = zone_interaction_mixed_model(long_df)
    print(mm.summary())

    stats_out = dict(
        mixed_model_summary=str(mm.summary()),
        mixed_model_params=dict(params=mm.params.to_dict(), pvalues=mm.pvalues.to_dict()),
        per_subject_slopes=slopes_df.to_dict(orient="records"),
        shuffle_tests={
            res["subject"]: dict(
                obs_reward_diff=res["shuffle_result"]["obs_reward_diff"],
                obs_choice_diff=res["shuffle_result"]["obs_choice_diff"],
                p_reward=res["shuffle_result"]["p_reward"],
                p_choice=res["shuffle_result"]["p_choice"],
                null_reward=res["shuffle_result"]["null_reward"].tolist(),
                null_choice=res["shuffle_result"]["null_choice"].tolist(),
                obs_slopes=res["shuffle_result"]["obs_slopes"],
            )
            for res in all_results
        },
    )
    with open("results/tables/zone_stats.json", "w") as f:
        json.dump(stats_out, f, indent=2, default=str)

    print("\nZone pipeline complete. Outputs in results/")


if __name__ == "__main__":
    main()
