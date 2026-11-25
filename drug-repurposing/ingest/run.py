import argparse
import logging
from pathlib import Path

from ingest import approvals, clinicaltrials, hetionet, pubmed, stringdb

log = logging.getLogger("ingest.run")

SOURCES = {
    "hetionet": hetionet.download,
    "stringdb": stringdb.download,
    "drugcentral": approvals.download,
    "clinicaltrials": clinicaltrials.download,
    "pubmed": pubmed.download,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, default=Path("data/raw"))
    parser.add_argument("--only", nargs="*", choices=sorted(SOURCES))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    for name in args.only or SOURCES:
        path = SOURCES[name](args.raw)
        log.info("%s ready at %s", name, path)


if __name__ == "__main__":
    main()
