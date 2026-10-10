"""
Time-separation matrices and inferential statistics relating PV correlation
to calendar-day distance and (true, corrected) time-of-day distance.

Session-pair correlation matrices are non-independent (each session appears in
multiple pairs), so the primary inferential test is a partial Mantel
permutation test, not a naive OLS on the vectorized pairs (which is included
only as an illustrative, non-authoritative secondary check).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats as sstats


def day_distance_matrix(dates: list) -> np.ndarray:
    d = np.array([pd.Timestamp(x).normalize() for x in dates])
    n = len(d)
    out = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            out[i, j] = abs((d[i] - d[j]).days)
    return out


def circadian_distance_matrix(hours: list) -> np.ndarray:
    h = np.array(hours, dtype=float)
    n = len(h)
    out = np.zeros((n, n))
    for i in range(n):
        for j in range(n):
            diff = abs(h[i] - h[j])
            out[i, j] = min(diff, 24 - diff)
    return out


def upper_tri(mat: np.ndarray) -> np.ndarray:
    iu = np.triu_indices_from(mat, k=1)
    return mat[iu]


def naive_ols(pv_mat, day_mat, circ_mat):
    """Illustrative only — ignores non-independence of paired observations."""
    import statsmodels.api as sm

    y = upper_tri(pv_mat)
    d = upper_tri(day_mat)
    c = upper_tri(circ_mat)
    valid = ~np.isnan(y)
    X = sm.add_constant(np.column_stack([d[valid], c[valid]]))
    model = sm.OLS(y[valid], X).fit()
    return model


def partial_correlation(y, x, z):
    """Partial Pearson correlation of y,x controlling for z (all 1D arrays)."""
    ry_x = np.corrcoef(y, z)[0, 1]
    rx_z = np.corrcoef(x, z)[0, 1]
    ryx = np.corrcoef(y, x)[0, 1]
    num = ryx - ry_x * rx_z
    den = np.sqrt((1 - ry_x**2) * (1 - rx_z**2))
    return num / den if den > 0 else np.nan


def partial_mantel(pv_mat, target_mat, control_mat, n_perm=10000, seed=0):
    """Partial Mantel test: does `target_mat` (e.g. circadian distance) predict
    `pv_mat` (PV correlation) after controlling for `control_mat` (day distance)?

    Null distribution built by permuting the *session order* of target_mat
    (standard Mantel permutation, preserves the matrix's internal structure)
    while holding pv_mat and control_mat fixed, and recomputing the partial
    correlation each time.
    """
    n = pv_mat.shape[0]
    rng = np.random.default_rng(seed)

    y_full = upper_tri(pv_mat)
    valid_full = ~np.isnan(y_full)

    def partial_r_for_perm(perm_idx):
        t_perm = target_mat[np.ix_(perm_idx, perm_idx)]
        y = y_full
        x = upper_tri(t_perm)
        z = upper_tri(control_mat)
        v = valid_full & ~np.isnan(x) & ~np.isnan(z)
        return partial_correlation(y[v], x[v], z[v])

    observed = partial_r_for_perm(np.arange(n))

    null = np.empty(n_perm)
    for k in range(n_perm):
        perm_idx = rng.permutation(n)
        null[k] = partial_r_for_perm(perm_idx)

    p_two_sided = (np.sum(np.abs(null) >= abs(observed)) + 1) / (n_perm + 1)
    return {
        "observed_partial_r": observed,
        "null_distribution": null,
        "p_value": p_two_sided,
        "n_perm": n_perm,
    }


def combine_pvalues_fisher(pvalues):
    """Combine independent per-subject p-values into one pooled p-value
    (Fisher's method) -- a permutation-grounded way to pool evidence across
    subjects without assuming a parametric mixed model."""
    from scipy.stats import combine_pvalues

    pvalues = [p for p in pvalues if p is not None and not np.isnan(p)]
    if len(pvalues) == 0:
        return {"statistic": np.nan, "p_value": np.nan, "n_subjects": 0}
    stat, p = combine_pvalues(pvalues, method="fisher")
    return {"statistic": stat, "p_value": p, "n_subjects": len(pvalues)}


def mixed_model_pooled(df: pd.DataFrame, dv="pv_corr", subject_col="subject", re_formula=None):
    """Pooled linear mixed-effects model across subjects:
    dv ~ day_distance + circadian_distance, random intercept per subject.

    This is a standard parametric approach (assumes normally-distributed
    residuals/random effects) included as a complementary pooled test
    alongside the assumption-free per-subject Mantel permutation tests and
    their Fisher combination -- it trades some robustness for the ability to
    estimate a single pooled effect size across all subjects at once.
    """
    import statsmodels.formula.api as smf

    d = df.dropna(subset=[dv, "day_distance", "circadian_distance"]).copy()
    model = smf.mixedlm(f"{dv} ~ day_distance + circadian_distance", d, groups=d[subject_col])
    result = model.fit(reml=True)
    return result


def zone_interaction_mixed_model(long_df: pd.DataFrame, dv="pv_corr", subject_col="subject"):
    """Primary confirmatory test for the zone-drift question:
    dv ~ day_distance * zone_category, random intercept per subject.
    A significant day_distance:zone_category interaction means the rate of
    decorrelation differs by zone type -- the core H1 test.
    """
    import statsmodels.formula.api as smf

    d = long_df.dropna(subset=[dv, "day_distance"]).copy()
    d["zone_category"] = pd.Categorical(d["zone_category"], categories=["corridor", "choice", "reward"])
    model = smf.mixedlm(f"{dv} ~ day_distance * C(zone_category, Treatment('corridor'))", d, groups=d[subject_col])
    return model.fit(reml=True)


def per_subject_zone_slopes(long_df: pd.DataFrame, dv="pv_corr"):
    """OLS slope of dv~day_distance separately per (subject, zone_category) --
    the descriptive quantity the interaction test and permutation test are
    both ultimately about."""
    rows = []
    for (subj, zone), sub in long_df.groupby(["subject", "zone_category"]):
        sub = sub.dropna(subset=[dv, "day_distance"])
        if len(sub) < 5 or sub["day_distance"].nunique() < 2:
            rows.append(dict(subject=subj, zone_category=zone, slope=np.nan, intercept=np.nan, r=np.nan, n=len(sub)))
            continue
        slope, intercept, r, p, se = sstats.linregress(sub["day_distance"], sub[dv])
        rows.append(dict(subject=subj, zone_category=zone, slope=slope, intercept=intercept, r=r, n=len(sub)))
    return pd.DataFrame(rows)


def mantel_simple(pv_mat, target_mat, n_perm=10000, seed=0):
    """Plain (non-partial) Mantel test between two matrices."""
    n = pv_mat.shape[0]
    rng = np.random.default_rng(seed)
    y_full = upper_tri(pv_mat)
    valid_full = ~np.isnan(y_full)

    def r_for_perm(perm_idx):
        t_perm = target_mat[np.ix_(perm_idx, perm_idx)]
        x = upper_tri(t_perm)
        v = valid_full & ~np.isnan(x)
        if np.std(y_full[v]) == 0 or np.std(x[v]) == 0:
            return np.nan
        return np.corrcoef(y_full[v], x[v])[0, 1]

    observed = r_for_perm(np.arange(n))
    null = np.array([r_for_perm(rng.permutation(n)) for _ in range(n_perm)])
    p = (np.sum(np.abs(null) >= abs(observed)) + 1) / (n_perm + 1)
    return {"observed_r": observed, "null_distribution": null, "p_value": p, "n_perm": n_perm}
