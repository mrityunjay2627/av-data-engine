from src.generate import generate_scenarios, write_raw_parquet
from src.ingest import run as ingest
from src.detect import run as detect
from src.featurize import run as featurize
from src.curate import run as curate
from src.embed import run as embed


def main():
    print("=" * 60)
    print("AV SCENARIO ENGINE — Full Pipeline Run")
    print("=" * 60)

    print("\n[1/6] GENERATE synthetic data")
    df = generate_scenarios()
    path = write_raw_parquet(df)
    print(f"  {len(df):,} rows → {path}\n")

    print("[2/6] INGEST → partitioned tracks")
    ingest()
    print()

    print("[3/6] DETECT → safety events")
    detect()
    print()

    print("[4/6] FEATURIZE → kinematic vectors")
    featurize()
    print()

    print("[5/6] CURATE → balanced subset")
    curate()
    print()

    print("[6/6] EMBED → LanceDB vector index")
    embed()

    print("\n" + "=" * 60)
    print("Pipeline complete. Next steps:")
    print("  python -m src.serve --stats                # catalog stats")
    print("  python -m src.serve --similar sc_00042      # find similar")
    print("  streamlit run analytics/dashboard.py        # dashboard")
    print("  dagster dev -m pipeline.definitions         # DAG UI")
    print("=" * 60)


if __name__ == "__main__":
    main()
