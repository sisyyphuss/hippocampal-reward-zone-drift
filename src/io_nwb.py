"""
Load DANDI:001775 NWB sessions (all 6 subjects) into compact, analysis-ready
session records.

Key correction vs. the dandiset's own `session_start_time` metadata field:
that field was found (by direct inspection, subject UT14 and independently
re-confirmed for UT13) to disagree with the true acquisition clock by hours,
inconsistently, session to session. The TRUE clock is reconstructed here from
the mutually-consistent Unix-epoch timestamps embedded in the position,
spike, and trial-interval data, for every subject -- not assumed to transfer
from UT14's correction.

Subjects vary structurally (confirmed by direct inspection): UT13 has ~2-3x
more units per session than UT06/UT14/UT15; Hisa's files are ecephys-only
(no `behavior+ecephys` combined file) and may lack Position entirely. This
loader is defensive: a session that doesn't fit the expected schema is
skipped with a logged reason rather than crashing the whole pipeline.
"""
from __future__ import annotations
import glob
import os
import pickle
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytz
from pynwb import NWBHDF5IO

CENTRAL = pytz.timezone("America/Chicago")

# quality thresholds applied to MountainSort4 output
MIN_ISOLATION = 0.90
MAX_NOISE_OVERLAP = 0.10
MIN_SPIKES = 100  # minimum spikes over the session to keep a unit

# Plausible absolute Unix-epoch range for this dandiset's collection years
# (2015-01-01 to 2026-01-01). Some subjects' position/spike timestamps turned
# out (confirmed by direct inspection, e.g. UT08) to be on a lab-internal
# RELATIVE clock (elapsed seconds since acquisition-system boot, ~millions of
# seconds) rather than true Unix epoch, unlike UT14/UT13 where the same field
# is absolute and directly usable. A session whose position timestamps don't
# fall in this range cannot have its true recording time verified from file
# contents alone and MUST be excluded, not silently mis-converted.
EPOCH_MIN = 1420070400.0  # 2015-01-01T00:00:00Z
EPOCH_MAX = 1767225600.0  # 2026-01-01T00:00:00Z

ALL_SUBJECTS = ["UT14", "UT06", "UT08", "UT13", "UT15", "Hisa"]


@dataclass
class SessionData:
    session_id: str
    subject_id: str
    file_path: str
    true_start_dt: datetime  # true local start time (from position data)
    true_end_dt: datetime
    reported_session_start_time: datetime  # the (unreliable) NWB metadata field
    pos_t: np.ndarray  # (N,) unix epoch seconds
    pos_xy: np.ndarray  # (N, 2) cm
    epochs: dict  # name -> list of (start,stop) unix epoch tuples
    units: pd.DataFrame  # filtered units table, index=unit id, col 'spike_times','nth_trode'
    n_units_raw: int
    n_units_kept: int
    n_tetrodes: int  # number of distinct tetrode groups on this session's probe
    trials_df: pd.DataFrame  # full trials table: choice, correct_arm, grasp_time, chewing_onset_time, etc.


@dataclass
class SkippedSession:
    file_path: str
    subject_id: str
    reason: str


def _local(ts_epoch: float) -> datetime:
    return datetime.fromtimestamp(ts_epoch, tz=timezone.utc).astimezone(CENTRAL)


def _find_position(nwb):
    """Search all processing modules for a Position/SpatialSeries interface,
    since not every subject necessarily uses the 'behavior' module name."""
    if nwb.processing is None:
        return None
    for mod_name, mod in nwb.processing.items():
        for iface_name, iface in mod.data_interfaces.items():
            if hasattr(iface, "spatial_series"):
                for ss_name, ss in iface.spatial_series.items():
                    return ss
    return None


def load_session(path: str) -> SessionData:
    with NWBHDF5IO(path, mode="r") as io:
        nwb = io.read()

        pos = _find_position(nwb)
        if pos is None:
            raise ValueError("no Position/SpatialSeries interface found")
        pos_t = np.asarray(pos.timestamps[:])
        pos_xy = np.asarray(pos.data[:])

        if not (EPOCH_MIN <= pos_t[0] <= EPOCH_MAX):
            raise ValueError(
                f"position timestamps are not absolute Unix epoch (first={pos_t[0]:.1f}) -- "
                "this session uses a lab-internal relative clock; true recording time is "
                "UNVERIFIABLE from file contents alone and this session is excluded rather "
                "than risk a silently wrong date"
            )
        if pos_xy.ndim != 2 or pos_xy.shape[1] < 2:
            raise ValueError(f"unexpected position data shape {pos_xy.shape}")
        pos_xy = pos_xy[:, :2]

        if nwb.intervals is None or "trials" not in nwb.intervals:
            raise ValueError("no 'trials' interval table found")
        trials = nwb.intervals["trials"].to_dataframe()
        if "epoch_type" not in trials.columns:
            raise ValueError("'trials' table has no 'epoch_type' column")

        epochs = {}
        for name in trials["epoch_type"].unique():
            sub = trials[trials.epoch_type == name]
            epochs[name] = list(zip(sub["start_time"].values, sub["stop_time"].values))

        if nwb.units is None:
            raise ValueError("no units table found")
        udf = nwb.units.to_dataframe()
        n_raw = len(udf)
        if "nth_trode" not in udf.columns:
            raise ValueError("units table has no 'nth_trode' column")

        required_qc_cols = {"isolation", "noise_overlap"}
        if required_qc_cols.issubset(udf.columns):
            keep = (
                (udf["isolation"] >= MIN_ISOLATION)
                & (udf["noise_overlap"] <= MAX_NOISE_OVERLAP)
                & (udf["spike_times"].apply(len) >= MIN_SPIKES)
            )
        else:
            # some sessions may lack curation-quality columns; fall back to spike-count only
            keep = udf["spike_times"].apply(len) >= MIN_SPIKES
        keep_cols = [c for c in ["spike_times", "nth_trode", "firing_rate", "isolation", "peak_snr"] if c in udf.columns]
        udf = udf.loc[keep, keep_cols].copy()

        true_start = _local(pos_t[0])
        true_end = _local(pos_t[-1])
        reported = nwb.session_start_time

        return SessionData(
            session_id=nwb.session_id,
            subject_id=nwb.subject.subject_id,
            file_path=path,
            true_start_dt=true_start,
            true_end_dt=true_end,
            reported_session_start_time=reported,
            pos_t=pos_t,
            pos_xy=pos_xy,
            epochs=epochs,
            units=udf,
            n_units_raw=n_raw,
            n_units_kept=len(udf),
            trials_df=trials,
            n_tetrodes=int(udf["nth_trode"].nunique()) if "nth_trode" in udf.columns else 0,
        )


def load_all_sessions(
    data_dir: str = "data",
    subjects: list[str] | None = None,
    cache_path: str = "results/cache/sessions_all.pkl",
    force: bool = False,
):
    """Load every session for every subject in `subjects` (default: all 6).
    `data_dir` should contain sub-{SUBJECT}/*.nwb folders (symlinks are fine).
    Returns (sessions, skipped) -- skipped sessions are logged, not silently dropped.
    """
    if subjects is None:
        subjects = ALL_SUBJECTS

    if os.path.exists(cache_path) and not force:
        with open(cache_path, "rb") as f:
            return pickle.load(f)

    sessions = []
    skipped = []
    for subj in subjects:
        subj_dir = os.path.join(data_dir, f"sub-{subj}")
        files = sorted(glob.glob(os.path.join(subj_dir, "*.nwb")))
        print(f"--- {subj}: {len(files)} files found in {subj_dir}")
        for f in files:
            try:
                print(f"  loading {f} ...")
                sessions.append(load_session(f))
            except Exception as e:
                reason = f"{type(e).__name__}: {e}"
                print(f"  SKIPPED {f}: {reason}")
                skipped.append(SkippedSession(file_path=f, subject_id=subj, reason=reason))

    sessions.sort(key=lambda s: (s.subject_id, s.true_start_dt))

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "wb") as f:
        pickle.dump((sessions, skipped), f)
    return sessions, skipped


if __name__ == "__main__":
    sessions, skipped = load_all_sessions(force=True)
    print(f"\nLoaded {len(sessions)} sessions across {len(set(s.subject_id for s in sessions))} subjects")
    print(f"Skipped {len(skipped)} sessions")
    for sk in skipped:
        print(f"  SKIPPED [{sk.subject_id}] {sk.file_path}: {sk.reason}")
    print()
    by_subj = {}
    for s in sessions:
        by_subj.setdefault(s.subject_id, []).append(s)
    for subj, sess_list in by_subj.items():
        print(f"\n=== {subj} ({len(sess_list)} sessions) ===")
        for s in sess_list:
            gap = (s.reported_session_start_time.timestamp() - s.pos_t[-1])
            print(
                f"  {s.session_id:20s} true_start={s.true_start_dt} "
                f"n_units_kept={s.n_units_kept}/{s.n_units_raw} n_tetrodes={s.n_tetrodes} "
                f"reported_gap={gap/60:.1f}min"
            )
