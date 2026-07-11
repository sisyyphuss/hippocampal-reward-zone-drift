"""
Population Vector (PV) correlation between two sessions' spatial maps.

Because spike sorting (MountainSort4) was run independently per session, single
units are NOT tracked across days. We solve cross-day comparability the way the
hardware actually allows: tetrode identity IS stable across days (same 32
physically-implanted tetrodes every session), so the primary PV is built on
tetrode-pooled multi-unit rate maps (a fixed, physically-grounded population
axis). A whole-ensemble mean-field correlation is computed alongside as a
simpler, identity-free sanity check.
"""
from __future__ import annotations
import numpy as np

MIN_CELLS_PER_BIN = 3  # minimum common tetrodes with data to trust a bin's PV
MIN_BINS_FOR_PAIR = 15  # minimum usable bins to trust a session-pair PV value


def tetrode_pv_correlation(mapsA, mapsB, visitedA, visitedB):
    """mapsA/mapsB: (n_trodes, Y, X) with NaN where a tetrode had no unit that day
    or a bin lacked occupancy. Returns (mean_r, n_bins_used, per_bin_r map)."""
    common_visited = visitedA & visitedB
    Y, X = common_visited.shape
    per_bin_r = np.full((Y, X), np.nan)

    ys, xs = np.where(common_visited)
    rs = []
    for y, x in zip(ys, xs):
        a = mapsA[:, y, x]
        b = mapsB[:, y, x]
        valid = ~np.isnan(a) & ~np.isnan(b)
        if valid.sum() < MIN_CELLS_PER_BIN:
            continue
        av, bv = a[valid], b[valid]
        if np.std(av) == 0 or np.std(bv) == 0:
            continue
        r = np.corrcoef(av, bv)[0, 1]
        per_bin_r[y, x] = r
        rs.append(r)

    if len(rs) < MIN_BINS_FOR_PAIR:
        return np.nan, len(rs), per_bin_r

    z = np.arctanh(np.clip(rs, -0.9999, 0.9999))
    mean_r = np.tanh(np.nanmean(z))
    return mean_r, len(rs), per_bin_r


def ensemble_mean_correlation(mapsA, mapsB, visitedA, visitedB):
    """Collapse the tetrode axis (nanmean per bin) then correlate the two
    resulting scalar fields over commonly-visited bins. Identity-free."""
    fieldA = np.nanmean(mapsA, axis=0)
    fieldB = np.nanmean(mapsB, axis=0)
    common_visited = visitedA & visitedB & ~np.isnan(fieldA) & ~np.isnan(fieldB)
    if common_visited.sum() < MIN_BINS_FOR_PAIR:
        return np.nan, int(common_visited.sum())
    a = fieldA[common_visited]
    b = fieldB[common_visited]
    if np.std(a) == 0 or np.std(b) == 0:
        return np.nan, int(common_visited.sum())
    r = np.corrcoef(a, b)[0, 1]
    return r, int(common_visited.sum())


def build_pv_matrices(all_tetrode_maps, all_visited):
    """all_tetrode_maps: list of (n_trodes,Y,X) arrays, one per session (already on
    the fixed shared tetrode axis). Returns (n,n) matrices: tetrode-PV, ensemble-r,
    n_bins_used."""
    n = len(all_tetrode_maps)
    pv_mat = np.full((n, n), np.nan)
    ens_mat = np.full((n, n), np.nan)
    nbins_mat = np.zeros((n, n), dtype=int)
    for i in range(n):
        for j in range(i, n):
            if i == j:
                pv_mat[i, j] = 1.0
                ens_mat[i, j] = 1.0
                continue
            r, nb, _ = tetrode_pv_correlation(all_tetrode_maps[i], all_tetrode_maps[j], all_visited[i], all_visited[j])
            pv_mat[i, j] = pv_mat[j, i] = r
            nbins_mat[i, j] = nbins_mat[j, i] = nb
            er, _ = ensemble_mean_correlation(all_tetrode_maps[i], all_tetrode_maps[j], all_visited[i], all_visited[j])
            ens_mat[i, j] = ens_mat[j, i] = er
    return pv_mat, ens_mat, nbins_mat
