"""
End-to-end pipeline: load sessions -> rate maps -> PV correlation matrices ->
time-separation matrices -> statistics. Saves everything needed for the
notebook/figures into results/.
"""
from __future__ import annotations
import json
import os
import pickle

import numpy as np
import pandas as pd

from io_nwb import load_all_sessions
from ratemaps import build_shared_grid, build_session_maps, tetrode_pooled_map, epoch_mask
from pv_correlation import build_pv_matrices
from stats_utils import day_distance_matrix, circadian_distance_matrix, naive_ols, partial_mantel, mantel_simple, upper_tri

ALL_TRODES = np.arange(1, 33)  # TT1-TT32, fixed physical hardware axis
BIN_SIZE = 4.0  # cm


def main():
    os.makedirs("results/cache", exist_ok=True)
    os.makedirs("results/tables", exist_ok=True)

    print("Loading sessions...")
    sessions = load_all_sessions(force=False)
    print(f"{len(sessions)} sessions loaded, sorted by true start time.")

    # ---- session summary table ----
    rows = []
    for s in sessions:
        gap_min = (s.reported_session_start_time.timestamp() - s.pos_t[-1]) / 60
        rows.append(dict(
            session_id=s.session_id,
            true_start=s.true_start_dt.isoformat(),
            true_hour=s.true_start_dt.hour + s.true_start_dt.minute / 60,
            reported_session_start_time=s.reported_session_start_time.isoformat(),
            reported_gap_minutes=gap_min,
            n_units=s.n_units_kept,
            session_duration_min=(s.pos_t[-1] - s.pos_t[0]) / 60,
        ))
    summary = pd.DataFrame(rows)
    summary.to_csv("results/tables/session_summary.csv", index=False)
    print(summary[["session_id", "true_start", "n_units", "reported_gap_minutes"]])

    results = {}
    for epoch_label, epoch_names in [("maze", ["dnmp"]), ("openfield", ["pre_run_OF", "post_run_OF"])]:
        print(f"\n=== Building rate maps for epoch group: {epoch_label} ({epoch_names}) ===")

        # merge epoch intervals into a synthetic combined epoch key per session for grid building
        for s in sessions:
            s.epochs[f"_combined_{epoch_label}"] = sum((s.epochs[n] for n in epoch_names), [])

        grid = build_shared_grid(sessions, f"_combined_{epoch_label}", bin_size=BIN_SIZE)
        print(f"grid shape {grid.shape}, x[{grid.xedges[0]:.1f},{grid.xedges[-1]:.1f}] y[{grid.yedges[0]:.1f},{grid.yedges[-1]:.1f}]")

        tetrode_maps = []
        visited_list = []
        occ_list = []
        unit_maps_list = []
        for s in sessions:
            occ, unit_maps, trode_ids, visited = build_session_maps(s, f"_combined_{epoch_label}", grid)
            tmap = tetrode_pooled_map(unit_maps, trode_ids, ALL_TRODES)
            tetrode_maps.append(tmap)
            visited_list.append(visited)
            occ_list.append(occ)
            unit_maps_list.append((unit_maps, trode_ids))
            print(f"  {s.session_id}: n_units={unit_maps.shape[0]}, visited_bins={visited.sum()}/{visited.size}")

        pv_mat, ens_mat, nbins_mat = build_pv_matrices(tetrode_maps, visited_list)

        results[epoch_label] = dict(
            grid=grid,
            tetrode_maps=tetrode_maps,
            visited_list=visited_list,
            occ_list=occ_list,
            unit_maps_list=unit_maps_list,
            pv_mat=pv_mat,
            ens_mat=ens_mat,
            nbins_mat=nbins_mat,
        )

    # ---- time separation matrices ----
    true_dates = [s.true_start_dt for s in sessions]
    true_hours = [s.true_start_dt.hour + s.true_start_dt.minute / 60 for s in sessions]
    reported_hours = [s.reported_session_start_time.hour + s.reported_session_start_time.minute / 60 for s in sessions]

    day_mat = day_distance_matrix(true_dates)
    circ_true_mat = circadian_distance_matrix(true_hours)
    circ_reported_mat = circadian_distance_matrix(reported_hours)  # the flawed version, kept for comparison/documentation

    np.savez(
        "results/cache/matrices.npz",
        day_mat=day_mat,
        circ_true_mat=circ_true_mat,
        circ_reported_mat=circ_reported_mat,
        pv_mat_maze=results["maze"]["pv_mat"],
        ens_mat_maze=results["maze"]["ens_mat"],
        nbins_mat_maze=results["maze"]["nbins_mat"],
        pv_mat_of=results["openfield"]["pv_mat"],
        ens_mat_of=results["openfield"]["ens_mat"],
        nbins_mat_of=results["openfield"]["nbins_mat"],
        session_ids=np.array([s.session_id for s in sessions]),
        true_hours=np.array(true_hours),
        reported_hours=np.array(reported_hours),
    )

    # ---- statistics ----
    stats_out = {}
    for epoch_label in ["maze", "openfield"]:
        pv_mat = results[epoch_label]["pv_mat"]
        print(f"\n=== Statistics: {epoch_label} (TRUE clock) ===")
        try:
            ols = naive_ols(pv_mat, day_mat, circ_true_mat)
            print(ols.summary())
            ols_params = dict(params=ols.params.tolist(), pvalues=ols.pvalues.tolist(), rsquared=ols.rsquared)
        except Exception as e:
            ols_params = {"error": str(e)}

        mantel_day = mantel_simple(pv_mat, day_mat, n_perm=5000, seed=1)
        mantel_circ_partial = partial_mantel(pv_mat, circ_true_mat, day_mat, n_perm=5000, seed=2)
        mantel_circ_partial_reported = partial_mantel(pv_mat, circ_reported_mat, day_mat, n_perm=5000, seed=3)

        print(f"Mantel (PV ~ day distance): r={mantel_day['observed_r']:.3f}, p={mantel_day['p_value']:.4f}")
        print(f"Partial Mantel (PV ~ TRUE circadian dist | day dist): r={mantel_circ_partial['observed_partial_r']:.3f}, p={mantel_circ_partial['p_value']:.4f}")
        print(f"Partial Mantel (PV ~ REPORTED(flawed) circadian dist | day dist): r={mantel_circ_partial_reported['observed_partial_r']:.3f}, p={mantel_circ_partial_reported['p_value']:.4f}")

        stats_out[epoch_label] = dict(
            ols=ols_params,
            mantel_day_r=mantel_day["observed_r"],
            mantel_day_p=mantel_day["p_value"],
            mantel_day_null=mantel_day["null_distribution"].tolist(),
            partial_mantel_circ_true_r=mantel_circ_partial["observed_partial_r"],
            partial_mantel_circ_true_p=mantel_circ_partial["p_value"],
            partial_mantel_circ_true_null=mantel_circ_partial["null_distribution"].tolist(),
            partial_mantel_circ_reported_r=mantel_circ_partial_reported["observed_partial_r"],
            partial_mantel_circ_reported_p=mantel_circ_partial_reported["p_value"],
        )

    with open("results/tables/stats_results.json", "w") as f:
        json.dump(stats_out, f, indent=2, default=str)

    # cache the full results object (rate maps etc.) for the notebook
    with open("results/cache/full_results.pkl", "wb") as f:
        pickle.dump({"sessions": sessions, "results": results, "day_mat": day_mat,
                     "circ_true_mat": circ_true_mat, "circ_reported_mat": circ_reported_mat,
                     "true_hours": true_hours, "reported_hours": reported_hours}, f)

    print("\nPipeline complete. Outputs in results/")


if __name__ == "__main__":
    main()
