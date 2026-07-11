"""
Occupancy and firing-rate maps, shared spatial bins across all sessions so
that any two sessions can be compared bin-for-bin.
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter

MIN_OCC_SEC = 0.15  # minimum occupancy time (s) for a bin to be considered "visited"
JUMP_SPEED_THRESHOLD_CM_S = 100.0  # a mouse cannot physically move faster than this


def clean_position(pos_t: np.ndarray, pos_xy: np.ndarray, speed_threshold=JUMP_SPEED_THRESHOLD_CM_S):
    """Flag position samples reached via a physically-impossible jump (tracking
    artifact, e.g. LED dropout/reacquisition) and linearly interpolate over them.

    Found to matter concretely for UT15, whose maze-corridor tracking showed a
    ~3.3% impossible-jump rate vs. ~0.3-0.4% for UT14/UT13 (8-10x higher) --
    investigated because it visibly distorted that subject's zone
    classification (see zones.py / notebooks/full_analysis_zones.ipynb
    Section 1). Re-running the reward-zone analysis on cleaned UT15 data
    reproduced the original result almost exactly (slope diff -0.0149 vs
    -0.0145, both p=0.002), confirming the finding was not a tracking
    artifact -- but this cleaning step is kept as a reusable utility since
    the same check is worth applying to any new subject/dataset by default.
    """
    xy = pos_xy.copy()
    dt = np.diff(pos_t)
    d = np.sqrt(np.sum(np.diff(xy, axis=0) ** 2, axis=1))
    speed = d / np.clip(dt, 1e-6, None)
    bad = np.zeros(len(pos_t), dtype=bool)
    bad[1:] |= speed > speed_threshold  # sample reached via an impossible jump
    n_bad = int(bad.sum())
    xy[bad] = np.nan
    for dim in range(2):
        col = xy[:, dim]
        nans = np.isnan(col)
        if nans.any() and (~nans).sum() > 2:
            col[nans] = np.interp(pos_t[nans], pos_t[~nans], col[~nans])
    return xy, n_bad


@dataclass
class SpatialGrid:
    xedges: np.ndarray
    yedges: np.ndarray
    bin_size: float

    @property
    def shape(self):
        return (len(self.yedges) - 1, len(self.xedges) - 1)


def build_shared_grid(sessions, epoch_name: str, bin_size: float = 4.0, pad: float = 5.0) -> SpatialGrid:
    """Union of spatial extent across all sessions during `epoch_name`, so every
    session is binned onto identical edges."""
    xmins, xmaxs, ymins, ymaxs = [], [], [], []
    for s in sessions:
        mask = epoch_mask(s, epoch_name)
        if mask.sum() == 0:
            continue
        xy = s.pos_xy[mask]
        xmins.append(np.nanmin(xy[:, 0])); xmaxs.append(np.nanmax(xy[:, 0]))
        ymins.append(np.nanmin(xy[:, 1])); ymaxs.append(np.nanmax(xy[:, 1]))
    xmin, xmax = min(xmins) - pad, max(xmaxs) + pad
    ymin, ymax = min(ymins) - pad, max(ymaxs) + pad
    xedges = np.arange(xmin, xmax + bin_size, bin_size)
    yedges = np.arange(ymin, ymax + bin_size, bin_size)
    return SpatialGrid(xedges=xedges, yedges=yedges, bin_size=bin_size)


def epoch_mask(session, epoch_name: str) -> np.ndarray:
    intervals = session.epochs.get(epoch_name, [])
    mask = np.zeros(session.pos_t.shape, dtype=bool)
    for (t0, t1) in intervals:
        mask |= (session.pos_t >= t0) & (session.pos_t <= t1)
    return mask


def occupancy_map(session, epoch_name: str, grid: SpatialGrid, smooth_sigma_bins: float = 1.0):
    mask = epoch_mask(session, epoch_name)
    t = session.pos_t[mask]
    xy = session.pos_xy[mask]
    if len(t) < 2:
        return np.zeros(grid.shape), mask

    # per-sample dwell time = time to next sample (clip to avoid gap artifacts)
    dt = np.diff(t, append=t[-1] + np.median(np.diff(t)))
    dt = np.clip(dt, 0, 0.5)

    occ, _, _ = np.histogram2d(xy[:, 1], xy[:, 0], bins=[grid.yedges, grid.xedges], weights=dt)
    occ_smooth = gaussian_filter(occ, sigma=smooth_sigma_bins)
    return occ_smooth, mask


def unit_rate_map(session, unit_row, epoch_name: str, grid: SpatialGrid, occ_raw_mask_sec: np.ndarray,
                   smooth_sigma_bins: float = 1.0):
    """Occupancy-normalized, Gaussian-smoothed rate map for one unit within one epoch."""
    intervals = session.epochs.get(epoch_name, [])
    spikes = unit_row["spike_times"]
    spikes = np.asarray(spikes)
    in_epoch = np.zeros(spikes.shape, dtype=bool)
    for (t0, t1) in intervals:
        in_epoch |= (spikes >= t0) & (spikes <= t1)
    spikes = spikes[in_epoch]
    if len(spikes) == 0:
        return np.zeros(grid.shape)

    # interpolate position at spike times
    x_at_spike = np.interp(spikes, session.pos_t, session.pos_xy[:, 0])
    y_at_spike = np.interp(spikes, session.pos_t, session.pos_xy[:, 1])

    spike_hist, _, _ = np.histogram2d(y_at_spike, x_at_spike, bins=[grid.yedges, grid.xedges])
    spike_smooth = gaussian_filter(spike_hist, sigma=smooth_sigma_bins)

    with np.errstate(divide="ignore", invalid="ignore"):
        rate = spike_smooth / occ_raw_mask_sec
    rate[occ_raw_mask_sec < MIN_OCC_SEC] = np.nan
    return rate


def build_session_maps(session, epoch_name: str, grid: SpatialGrid):
    """Returns:
       occ: (Y,X) occupancy seconds
       unit_maps: (n_units, Y, X) rate maps
       trode_ids: (n_units,) tetrode id per unit
       visited: (Y,X) bool, bins with enough occupancy
    """
    occ, _ = occupancy_map(session, epoch_name, grid)
    visited = occ >= MIN_OCC_SEC

    unit_maps = []
    trode_ids = []
    for _, row in session.units.iterrows():
        rm = unit_rate_map(session, row, epoch_name, grid, occ)
        unit_maps.append(rm)
        trode_ids.append(row["nth_trode"])
    unit_maps = np.array(unit_maps) if unit_maps else np.zeros((0, *grid.shape))
    trode_ids = np.array(trode_ids)
    return occ, unit_maps, trode_ids, visited


def tetrode_pooled_map(unit_maps: np.ndarray, trode_ids: np.ndarray, all_trode_ids: np.ndarray):
    """Average the (already occupancy-normalized) unit rate maps sharing a tetrode,
    producing a (n_trodes, Y, X) array on a FIXED tetrode axis (all_trode_ids) so
    every session has the same population-vector dimensionality regardless of how
    many units were isolated that day. Tetrodes with 0 units that session -> NaN.
    """
    Y, X = unit_maps.shape[1:] if unit_maps.shape[0] else (0, 0)
    out = np.full((len(all_trode_ids), *unit_maps.shape[1:]), np.nan)
    for i, tid in enumerate(all_trode_ids):
        sel = trode_ids == tid
        if sel.sum() > 0:
            out[i] = np.nanmean(unit_maps[sel], axis=0)
    return out
