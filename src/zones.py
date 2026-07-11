"""
Classify maze spatial bins into behaviorally-relevant categories: reward
zone (near the food port reached at the end of a correct trial), choice
zone (the stem segment nearest the L/R split), and corridor (everything
else visited). Zones are defined ONCE PER SUBJECT, pooling trial data
across all of that subject's sessions, since the physical maze and reward
port locations are fixed hardware, not something that should be
re-estimated (and potentially drift) session to session.
"""
from __future__ import annotations
from dataclasses import dataclass

import numpy as np
from scipy.ndimage import binary_dilation

from ratemaps import epoch_mask

REWARD_RADIUS_CM = 10.0
CHOICE_DILATION_ITERS = 1  # how many bins to grow the arm-exclusive region to find the adjoining choice zone
MIN_OCC_SEC_FOR_ZONES = 0.15


@dataclass
class ZoneMasks:
    reward: np.ndarray   # bool (Y,X)
    choice: np.ndarray   # bool (Y,X)
    corridor: np.ndarray  # bool (Y,X)
    reward_centroids: dict  # {'L': (x,y) or None, 'R': (x,y) or None}
    n_reward_events: dict   # {'L': n, 'R': n}


def _trial_time_windows(trials_df, choice_side, epoch_name="dnmp"):
    sub = trials_df[(trials_df.epoch_type == epoch_name) & (trials_df.choice == choice_side)]
    return list(zip(sub["start_time"].values, sub["stop_time"].values))


def _mask_from_windows(pos_t, windows):
    mask = np.zeros(pos_t.shape, dtype=bool)
    for t0, t1 in windows:
        mask |= (pos_t >= t0) & (pos_t <= t1)
    return mask


def _reward_positions(session, choice_side):
    """Interpolate position at grasp_time (fallback: chewing_onset_time) for
    every correct-choice trial of the given side."""
    trials = session.trials_df
    sub = trials[(trials.epoch_type == "dnmp") & (trials.choice == choice_side)]
    times = sub["grasp_time"].where(sub["grasp_time"].notna(), sub["chewing_onset_time"])
    times = times.dropna().values
    times = times[(times >= session.pos_t[0]) & (times <= session.pos_t[-1])]
    if len(times) == 0:
        return np.zeros((0, 2))
    x = np.interp(times, session.pos_t, session.pos_xy[:, 0])
    y = np.interp(times, session.pos_t, session.pos_xy[:, 1])
    return np.column_stack([x, y])


def occupancy_for_choice(sessions, grid, choice_side):
    """Pooled occupancy map across all sessions, restricted to trials of one choice side."""
    from scipy.ndimage import gaussian_filter

    occ_total = np.zeros(grid.shape)
    for s in sessions:
        windows = _trial_time_windows(s.trials_df, choice_side)
        if not windows:
            continue
        mask = _mask_from_windows(s.pos_t, windows)
        if mask.sum() < 2:
            continue
        t = s.pos_t[mask]
        xy = s.pos_xy[mask]
        dt = np.clip(np.diff(t, append=t[-1] + np.median(np.diff(t))), 0, 0.5)
        occ, _, _ = np.histogram2d(xy[:, 1], xy[:, 0], bins=[grid.yedges, grid.xedges], weights=dt)
        occ_total += occ
    return gaussian_filter(occ_total, sigma=1.0)


def define_subject_zones(sessions, grid, reward_radius=REWARD_RADIUS_CM) -> ZoneMasks:
    occ_L = occupancy_for_choice(sessions, grid, "L")
    occ_R = occupancy_for_choice(sessions, grid, "R")
    visited_L = occ_L >= MIN_OCC_SEC_FOR_ZONES
    visited_R = occ_R >= MIN_OCC_SEC_FOR_ZONES

    shared = visited_L & visited_R
    exclusive = visited_L ^ visited_R  # visited by exactly one side

    # choice zone: shared/stem bins directly adjoining the arm-exclusive region
    exclusive_dilated = binary_dilation(exclusive, iterations=CHOICE_DILATION_ITERS)
    choice_zone = shared & exclusive_dilated

    # reward zone: union of L and R reward-event positions, radius around each centroid
    reward_mask = np.zeros(grid.shape, dtype=bool)
    centroids = {}
    n_events = {}
    yy, xx = np.meshgrid(
        (grid.yedges[:-1] + grid.yedges[1:]) / 2,
        (grid.xedges[:-1] + grid.xedges[1:]) / 2,
        indexing="ij",
    )
    for side in ["L", "R"]:
        pts = _reward_positions_pooled(sessions, side)
        n_events[side] = len(pts)
        if len(pts) == 0:
            centroids[side] = None
            continue
        cx, cy = np.median(pts[:, 0]), np.median(pts[:, 1])
        centroids[side] = (cx, cy)
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        reward_mask |= dist <= reward_radius

    visited_any = visited_L | visited_R
    reward_mask &= visited_any
    choice_zone &= visited_any & ~reward_mask
    corridor = visited_any & ~reward_mask & ~choice_zone

    return ZoneMasks(reward=reward_mask, choice=choice_zone, corridor=corridor,
                      reward_centroids=centroids, n_reward_events=n_events)


def _reward_positions_pooled(sessions, choice_side):
    pts = [_reward_positions(s, choice_side) for s in sessions]
    pts = [p for p in pts if len(p)]
    return np.concatenate(pts, axis=0) if pts else np.zeros((0, 2))


def zone_visited_mask(zone_masks: ZoneMasks, category: str, session_visited: np.ndarray) -> np.ndarray:
    """Intersect a subject-level zone category with one session's actual visited bins."""
    zone = getattr(zone_masks, category)
    return zone & session_visited


def zone_pv_matrices(tetrode_maps, visited_list, zone_masks: ZoneMasks):
    """PV correlation matrix per zone category, reusing the same tetrode-pooled
    rate maps already computed for the whole-maze analysis -- only the visited
    mask changes per category."""
    from pv_correlation import build_pv_matrices

    out = {}
    for category in ["reward", "choice", "corridor"]:
        masked_visited = [zone_visited_mask(zone_masks, category, v) for v in visited_list]
        pv_mat, ens_mat, nbins_mat = build_pv_matrices(tetrode_maps, masked_visited)
        out[category] = dict(pv_mat=pv_mat, ens_mat=ens_mat, nbins_mat=nbins_mat)
    return out


def random_size_matched_zones(zone_masks: ZoneMasks, rng: np.random.Generator) -> ZoneMasks:
    """Occupancy-matched shuffle control: randomly reassign the SAME visited
    bins to pseudo-categories of the SAME sizes as the real reward/choice/
    corridor zones. Tests whether the observed zone effect exceeds what a
    same-sized, randomly-placed region would show, given the real occupancy
    structure of those bins."""
    visited_any = zone_masks.reward | zone_masks.choice | zone_masks.corridor
    idx = np.argwhere(visited_any)
    n_reward = int(zone_masks.reward.sum())
    n_choice = int(zone_masks.choice.sum())
    perm = rng.permutation(len(idx))
    reward_idx = idx[perm[:n_reward]]
    choice_idx = idx[perm[n_reward:n_reward + n_choice]]
    corridor_idx = idx[perm[n_reward + n_choice:]]

    def to_mask(coords):
        m = np.zeros(zone_masks.reward.shape, dtype=bool)
        if len(coords):
            m[coords[:, 0], coords[:, 1]] = True
        return m

    return ZoneMasks(
        reward=to_mask(reward_idx), choice=to_mask(choice_idx), corridor=to_mask(corridor_idx),
        reward_centroids=zone_masks.reward_centroids, n_reward_events=zone_masks.n_reward_events,
    )


def slope_diff_statistic(tetrode_maps, visited_list, zone_masks, day_mat):
    """Observed statistic for the shuffle test: (reward slope) - (corridor slope),
    and (choice slope) - (corridor slope), using calendar-day distance."""
    from scipy import stats as sstats

    zone_pvs = zone_pv_matrices(tetrode_maps, visited_list, zone_masks)
    iu = np.triu_indices_from(day_mat, k=1)
    d = day_mat[iu]
    slopes = {}
    for category in ["reward", "choice", "corridor"]:
        y = zone_pvs[category]["pv_mat"][iu]
        valid = ~np.isnan(y)
        if valid.sum() < 5 or np.std(d[valid]) == 0:
            slopes[category] = np.nan
            continue
        slope, *_ = sstats.linregress(d[valid], y[valid])
        slopes[category] = slope
    return slopes["reward"] - slopes["corridor"], slopes["choice"] - slopes["corridor"], slopes


def occupancy_matched_shuffle_test(tetrode_maps, visited_list, zone_masks, day_mat, n_perm=500, seed=0):
    rng = np.random.default_rng(seed)
    obs_reward_diff, obs_choice_diff, obs_slopes = slope_diff_statistic(tetrode_maps, visited_list, zone_masks, day_mat)

    null_reward, null_choice = np.empty(n_perm), np.empty(n_perm)
    for k in range(n_perm):
        pseudo_zones = random_size_matched_zones(zone_masks, rng)
        rd, cd, _ = slope_diff_statistic(tetrode_maps, visited_list, pseudo_zones, day_mat)
        null_reward[k], null_choice[k] = rd, cd

    p_reward = (np.sum(np.abs(null_reward) >= abs(obs_reward_diff)) + 1) / (n_perm + 1)
    p_choice = (np.sum(np.abs(null_choice) >= abs(obs_choice_diff)) + 1) / (n_perm + 1)
    return dict(
        obs_reward_diff=obs_reward_diff, obs_choice_diff=obs_choice_diff, obs_slopes=obs_slopes,
        null_reward=null_reward, null_choice=null_choice,
        p_reward=p_reward, p_choice=p_choice, n_perm=n_perm,
    )
