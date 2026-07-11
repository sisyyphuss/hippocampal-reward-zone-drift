"""
Investigates the zone-classification irregularity found in UT15 (Section 1 of
full_analysis_zones.ipynb): quantifies position-tracking jump-artifact rates
across all three subjects, localizes them for UT15, and re-runs the
reward-vs-corridor zone analysis on cleaned UT15 position data to check
whether the finding survives.

Run standalone: `python src/investigate_ut15_tracking.py`
Writes results/tables/ut15_tracking_investigation.json for the notebook.
"""
from __future__ import annotations
import json
import os
import zlib

import numpy as np

from io_nwb import load_all_sessions
from ratemaps import build_shared_grid, build_session_maps, tetrode_pooled_map, clean_position, JUMP_SPEED_THRESHOLD_CM_S
from zones import define_subject_zones, occupancy_matched_shuffle_test
from stats_utils import day_distance_matrix

SUBJECTS = ["UT14", "UT13", "UT15"]


def trode_axis_for_subject(sessions):
    max_trode = 0
    for s in sessions:
        if len(s.units):
            max_trode = max(max_trode, int(s.units["nth_trode"].max()))
    return np.arange(1, max_trode + 1)


def jump_rate_stats(sessions):
    total, jumps, corridor_total, corridor_jumps = 0, 0, 0, 0
    for s in sessions:
        dt = np.diff(s.pos_t)
        d = np.sqrt(np.sum(np.diff(s.pos_xy, axis=0) ** 2, axis=1))
        speed = d / np.clip(dt, 1e-6, None)
        total += len(speed)
        jumps += int((speed > JUMP_SPEED_THRESHOLD_CM_S).sum())
        in_corridor = (s.pos_xy[:-1, 1] > -4) & (s.pos_xy[:-1, 1] < 6)
        corridor_total += int(in_corridor.sum())
        corridor_jumps += int(((speed > JUMP_SPEED_THRESHOLD_CM_S) & in_corridor).sum())
    return dict(total=total, jumps=jumps, pct=100 * jumps / total,
                corridor_total=corridor_total, corridor_jumps=corridor_jumps,
                corridor_pct=100 * corridor_jumps / corridor_total)


def run_reward_zone_test(sessions, label):
    sessions = sorted(sessions, key=lambda s: s.true_start_dt)
    for s in sessions:
        s.epochs["_combined_maze"] = s.epochs["dnmp"]
    grid = build_shared_grid(sessions, "_combined_maze", bin_size=4.0)
    all_trodes = trode_axis_for_subject(sessions)
    zone_masks = define_subject_zones(sessions, grid)

    tetrode_maps, visited_list = [], []
    for s in sessions:
        occ, unit_maps, trode_ids, visited = build_session_maps(s, "_combined_maze", grid)
        tetrode_maps.append(tetrode_pooled_map(unit_maps, trode_ids, all_trodes))
        visited_list.append(visited)

    day_mat = day_distance_matrix([s.true_start_dt for s in sessions])
    seed = zlib.crc32(label.encode()) % (2**31 - 1)
    result = occupancy_matched_shuffle_test(tetrode_maps, visited_list, zone_masks, day_mat, n_perm=500, seed=seed)
    return dict(
        label=label, n_reward_bins=int(zone_masks.reward.sum()), n_choice_bins=int(zone_masks.choice.sum()),
        reward_diff=result["obs_reward_diff"], reward_p=result["p_reward"],
        choice_diff=result["obs_choice_diff"], choice_p=result["p_choice"],
    )


def main():
    os.makedirs("results/tables", exist_ok=True)
    sessions, skipped = load_all_sessions(subjects=SUBJECTS, force=False)
    by_subject = {}
    for s in sessions:
        by_subject.setdefault(s.subject_id, []).append(s)

    print("=== Tracking jump-rate comparison ===")
    jump_stats = {}
    for subj in SUBJECTS:
        stats = jump_rate_stats(by_subject[subj])
        jump_stats[subj] = stats
        print(f"{subj}: all-positions jump rate={stats['pct']:.2f}%, "
              f"corridor-only jump rate={stats['corridor_pct']:.2f}%")

    print("\n=== UT15: original (uncleaned) vs. position-cleaned ===")
    uncleaned = run_reward_zone_test(by_subject["UT15"], "UT15_uncleaned")
    print(f"uncleaned: {uncleaned}")

    cleaned_sessions = by_subject["UT15"]
    n_bad_total = 0
    for s in cleaned_sessions:
        cleaned_xy, n_bad = clean_position(s.pos_t, s.pos_xy)
        s.pos_xy = cleaned_xy
        n_bad_total += n_bad
    print(f"cleaned {n_bad_total} flagged samples via interpolation")
    cleaned = run_reward_zone_test(cleaned_sessions, "UT15_cleaned")
    print(f"cleaned: {cleaned}")

    with open("results/tables/ut15_tracking_investigation.json", "w") as f:
        json.dump(dict(jump_stats=jump_stats, n_cleaned_samples=n_bad_total,
                        uncleaned=uncleaned, cleaned=cleaned), f, indent=2, default=str)
    print("\nSaved results/tables/ut15_tracking_investigation.json")


if __name__ == "__main__":
    main()
