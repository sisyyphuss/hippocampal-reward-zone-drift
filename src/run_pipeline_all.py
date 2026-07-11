"""
Multi-animal end-to-end pipeline for DANDI:001775 (all 6 subjects).

For each subject with usable data (spike-sorted units + position + trial
intervals), builds rate maps, tetrode-level and ensemble PV correlation
matrices, and true/reported time-separation matrices, exactly as for UT14
alone -- then pools everything into a single long-format table for
cross-subject statistics (per-subject Mantel tests, Fisher-combined pooled
p-value, and a pooled linear mixed-effects model with subject as a random
effect).

Subjects are NOT assumed to be structurally identical -- Hisa is a known
pharmacology pilot with no spike-sorted units (excluded automatically by the
loader) and is reported as excluded, not silently dropped.
"""
from __future__ import annotations
import json
import os
import pickle

import numpy as np
import pandas as pd

from io_nwb import load_all_sessions, ALL_SUBJECTS
from ratemaps import build_shared_grid, build_session_maps, tetrode_pooled_map
from pv_correlation import build_pv_matrices
import zlib

from stats_utils import (
    day_distance_matrix, circadian_distance_matrix,
    partial_mantel, mantel_simple, upper_tri, combine_pvalues_fisher, mixed_model_pooled,
)


def stable_seed(*parts) -> int:
    """Deterministic seed from string parts (Python's built-in hash() is
    randomized per-process via PYTHONHASHSEED and is NOT safe here)."""
    return zlib.crc32("|".join(str(p) for p in parts).encode()) % (2**31)

BIN_SIZE = 4.0  # cm
MIN_SESSIONS_FOR_SUBJECT = 5  # need at least this many valid sessions to build a PV matrix


def trode_axis_for_subject(sessions):
    max_trode = 0
    for s in sessions:
        if len(s.units):
            max_trode = max(max_trode, int(s.units["nth_trode"].max()))
    return np.arange(1, max_trode + 1) if max_trode > 0 else np.array([])


def process_subject(subj, sessions):
    """Returns a dict of results for one subject, or None if too few sessions."""
    if len(sessions) < MIN_SESSIONS_FOR_SUBJECT:
        print(f"  [{subj}] only {len(sessions)} valid sessions (<{MIN_SESSIONS_FOR_SUBJECT}) -- SKIPPING subject")
        return None

    all_trodes = trode_axis_for_subject(sessions)
    print(f"  [{subj}] {len(sessions)} sessions, {len(all_trodes)} tetrode slots")

    subj_results = {}
    for epoch_label, epoch_names in [("maze", ["dnmp"]), ("openfield", ["pre_run_OF", "post_run_OF"])]:
        for s in sessions:
            available = [n for n in epoch_names if n in s.epochs]
            s.epochs[f"_combined_{epoch_label}"] = sum((s.epochs[n] for n in available), [])

        grid = build_shared_grid(sessions, f"_combined_{epoch_label}", bin_size=BIN_SIZE)

        tetrode_maps, visited_list, occ_list, unit_maps_list = [], [], [], []
        for s in sessions:
            occ, unit_maps, trode_ids, visited = build_session_maps(s, f"_combined_{epoch_label}", grid)
            tmap = tetrode_pooled_map(unit_maps, trode_ids, all_trodes) if len(all_trodes) else np.zeros((0, *grid.shape))
            tetrode_maps.append(tmap)
            visited_list.append(visited)
            occ_list.append(occ)
            unit_maps_list.append((unit_maps, trode_ids))

        pv_mat, ens_mat, nbins_mat = build_pv_matrices(tetrode_maps, visited_list)

        subj_results[epoch_label] = dict(
            grid=grid, tetrode_maps=tetrode_maps, visited_list=visited_list,
            occ_list=occ_list, unit_maps_list=unit_maps_list,
            pv_mat=pv_mat, ens_mat=ens_mat, nbins_mat=nbins_mat,
        )

    true_dates = [s.true_start_dt for s in sessions]
    true_hours = [s.true_start_dt.hour + s.true_start_dt.minute / 60 for s in sessions]
    reported_hours = [s.reported_session_start_time.hour + s.reported_session_start_time.minute / 60 for s in sessions]

    day_mat = day_distance_matrix(true_dates)
    circ_true_mat = circadian_distance_matrix(true_hours)
    circ_reported_mat = circadian_distance_matrix(reported_hours)

    return dict(
        subject=subj, sessions=sessions, results=subj_results,
        day_mat=day_mat, circ_true_mat=circ_true_mat, circ_reported_mat=circ_reported_mat,
        true_hours=np.array(true_hours), reported_hours=np.array(reported_hours),
        session_ids=[s.session_id for s in sessions],
        all_trodes=all_trodes,
    )


def build_long_table(all_subject_results, epoch_label):
    """One row per within-subject session pair, across all subjects."""
    rows = []
    for subj_res in all_subject_results:
        subj = subj_res["subject"]
        pv_mat = subj_res["results"][epoch_label]["pv_mat"]
        ens_mat = subj_res["results"][epoch_label]["ens_mat"]
        day_mat = subj_res["day_mat"]
        circ_true = subj_res["circ_true_mat"]
        circ_rep = subj_res["circ_reported_mat"]
        session_ids = subj_res["session_ids"]
        n = len(session_ids)
        for i in range(n):
            for j in range(i + 1, n):
                rows.append(dict(
                    subject=subj, session_i=session_ids[i], session_j=session_ids[j],
                    pv_corr=pv_mat[i, j], ens_corr=ens_mat[i, j],
                    day_distance=day_mat[i, j],
                    circadian_distance=circ_true[i, j],
                    circadian_distance_reported=circ_rep[i, j],
                ))
    return pd.DataFrame(rows)


def main():
    os.makedirs("results/cache", exist_ok=True)
    os.makedirs("results/tables", exist_ok=True)

    print("Loading all sessions for all subjects...")
    sessions, skipped = load_all_sessions(subjects=ALL_SUBJECTS, force=False)
    print(f"\n{len(sessions)} sessions loaded, {len(skipped)} skipped.\n")

    by_subject = {}
    for s in sessions:
        by_subject.setdefault(s.subject_id, []).append(s)
    for subj in by_subject:
        by_subject[subj].sort(key=lambda s: s.true_start_dt)

    # session-level QC/summary table (every subject, including skipped)
    rows = []
    for s in sessions:
        gap_min = (s.reported_session_start_time.timestamp() - s.pos_t[-1]) / 60
        rows.append(dict(
            subject=s.subject_id, session_id=s.session_id,
            true_start=s.true_start_dt.isoformat(), true_hour=s.true_start_dt.hour + s.true_start_dt.minute / 60,
            reported_session_start_time=s.reported_session_start_time.isoformat(),
            reported_gap_minutes=gap_min, n_units=s.n_units_kept, n_tetrodes=s.n_tetrodes,
            session_duration_min=(s.pos_t[-1] - s.pos_t[0]) / 60, status="included",
        ))
    for sk in skipped:
        rows.append(dict(subject=sk.subject_id, session_id=os.path.basename(sk.file_path),
                          status=f"SKIPPED: {sk.reason}"))
    all_summary = pd.DataFrame(rows)
    all_summary.to_csv("results/tables/all_subjects_session_summary.csv", index=False)
    print(all_summary.groupby("subject").size())

    print("\nProcessing each subject (rate maps + PV matrices)...")
    all_subject_results = []
    for subj in ALL_SUBJECTS:
        sess_list = by_subject.get(subj, [])
        print(f"\n=== {subj}: {len(sess_list)} candidate sessions ===")
        res = process_subject(subj, sess_list)
        if res is not None:
            all_subject_results.append(res)

    included_subjects = [r["subject"] for r in all_subject_results]
    print(f"\nSubjects included in PV analysis: {included_subjects}")

    # cache per-subject full results (rate maps etc.)
    with open("results/cache/all_subjects_full_results.pkl", "wb") as f:
        pickle.dump(all_subject_results, f)

    # ---- pooled long-format tables + statistics ----
    pooled_stats = {}
    long_tables = {}
    for epoch_label in ["maze", "openfield"]:
        print(f"\n\n########## EPOCH: {epoch_label} ##########")
        long_df = build_long_table(all_subject_results, epoch_label)
        long_tables[epoch_label] = long_df
        long_df.to_csv(f"results/tables/pooled_pairs_{epoch_label}.csv", index=False)

        per_subject_stats = {}
        day_pvals, circ_pvals = [], []
        for subj_res in all_subject_results:
            subj = subj_res["subject"]
            pv_mat = subj_res["results"][epoch_label]["pv_mat"]
            day_mat = subj_res["day_mat"]
            circ_true_mat = subj_res["circ_true_mat"]

            mantel_day = mantel_simple(pv_mat, day_mat, n_perm=3000, seed=stable_seed(subj, "day"))
            partial_circ = partial_mantel(pv_mat, circ_true_mat, day_mat, n_perm=3000, seed=stable_seed(subj, "circ"))

            per_subject_stats[subj] = dict(
                n_sessions=len(subj_res["session_ids"]),
                mantel_day_r=mantel_day["observed_r"], mantel_day_p=mantel_day["p_value"],
                partial_circ_r=partial_circ["observed_partial_r"], partial_circ_p=partial_circ["p_value"],
                true_hour_min=float(subj_res["true_hours"].min()), true_hour_max=float(subj_res["true_hours"].max()),
                true_hour_span=float(subj_res["true_hours"].max() - subj_res["true_hours"].min()),
            )
            day_pvals.append(mantel_day["p_value"])
            circ_pvals.append(partial_circ["p_value"])
            print(f"  [{subj}] n={len(subj_res['session_ids'])}: Mantel day r={mantel_day['observed_r']:.3f} p={mantel_day['p_value']:.4f} | "
                  f"partial circadian r={partial_circ['observed_partial_r']:.3f} p={partial_circ['p_value']:.4f}")

        fisher_day = combine_pvalues_fisher(day_pvals)
        fisher_circ = combine_pvalues_fisher(circ_pvals)
        print(f"  POOLED (Fisher): day-distance p={fisher_day['p_value']:.5f} (n={fisher_day['n_subjects']}) | "
              f"circadian p={fisher_circ['p_value']:.5f} (n={fisher_circ['n_subjects']})")

        try:
            mm = mixed_model_pooled(long_df, dv="pv_corr", subject_col="subject")
            mixed_model_summary = str(mm.summary())
            mixed_model_params = dict(params=mm.params.to_dict(), pvalues=mm.pvalues.to_dict())
            print(mixed_model_summary)
        except Exception as e:
            mixed_model_summary = f"FAILED: {e}"
            mixed_model_params = {"error": str(e)}

        pooled_stats[epoch_label] = dict(
            per_subject=per_subject_stats,
            fisher_day=fisher_day, fisher_circ=fisher_circ,
            mixed_model_summary=mixed_model_summary, mixed_model_params=mixed_model_params,
            n_pairs_total=len(long_df),
        )

    with open("results/tables/pooled_stats.json", "w") as f:
        json.dump(pooled_stats, f, indent=2, default=str)

    print("\n\nMulti-animal pipeline complete. Outputs in results/")


if __name__ == "__main__":
    main()
