"""One-off structural inspection of a UT14 NWB file to ground the extraction code in reality."""
import sys
from pynwb import NWBHDF5IO

path = sys.argv[1] if len(sys.argv) > 1 else "data/sub-UT14/sub-UT14_ses-Day10_behavior+ecephys.nwb"

with NWBHDF5IO(path, mode="r") as io:
    nwbfile = io.read()

    print("=" * 70)
    print("SESSION METADATA")
    print("=" * 70)
    print("session_id:", nwbfile.session_id)
    print("session_start_time:", nwbfile.session_start_time)
    print("session_description:", nwbfile.session_description)
    print("subject:", nwbfile.subject)

    print("\n" + "=" * 70)
    print("ELECTRODES TABLE")
    print("=" * 70)
    et = nwbfile.electrodes
    print("columns:", et.colnames)
    df = et.to_dataframe()
    print(df.head(15))
    print("shape:", df.shape)
    print("unique groups:", df["group_name"].unique() if "group_name" in df.columns else "n/a")

    print("\n" + "=" * 70)
    print("UNITS TABLE")
    print("=" * 70)
    ut = nwbfile.units
    print("columns:", ut.colnames)
    udf = ut.to_dataframe()
    print(udf.head(10))
    print("n units:", len(udf))
    print("dtypes:\n", udf.dtypes)

    print("\n" + "=" * 70)
    print("PROCESSING MODULES")
    print("=" * 70)
    for mod_name, mod in nwbfile.processing.items():
        print(f"-- module: {mod_name}")
        for iface_name, iface in mod.data_interfaces.items():
            print(f"   interface: {iface_name} ({type(iface).__name__})")
            if hasattr(iface, "spatial_series"):
                for ss_name, ss in iface.spatial_series.items():
                    print(f"      spatial_series: {ss_name} data shape={ss.data.shape} unit={ss.unit}")
                    print(f"        timestamps available: {ss.timestamps is not None}")
                    if ss.timestamps is not None:
                        print(f"        n timestamps: {len(ss.timestamps)} first5={ss.timestamps[:5]} last={ss.timestamps[-1]}")
                    print(f"        data sample:\n{ss.data[:5]}")

    print("\n" + "=" * 70)
    print("INTERVALS / TRIALS")
    print("=" * 70)
    print("nwbfile.intervals keys:", list(nwbfile.intervals.keys()) if nwbfile.intervals else None)
    if nwbfile.intervals:
        for name, tbl in nwbfile.intervals.items():
            print(f"-- {name}: columns={tbl.colnames}")
            tdf = tbl.to_dataframe()
            print(tdf.head(10))
            print("shape:", tdf.shape)

    print("\n" + "=" * 70)
    print("EPOCHS (if separate from intervals)")
    print("=" * 70)
    if nwbfile.epochs is not None:
        print(nwbfile.epochs.to_dataframe().head(10))
