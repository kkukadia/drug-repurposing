NODE_COLUMNS = ["node_id", "kind", "ext_id", "name", "source", "source_version"]
EDGE_COLUMNS = ["src", "dst", "etype", "source", "source_version", "weight"]
INDICATION_COLUMNS = ["drug_node", "disease_node", "year", "label_source"]

KIND_NAMES = {
    "Anatomy": "Anatomy",
    "Biological Process": "BiologicalProcess",
    "Cellular Component": "CellularComponent",
    "Compound": "Compound",
    "Disease": "Disease",
    "Gene": "Gene",
    "Molecular Function": "MolecularFunction",
    "Pathway": "Pathway",
    "Pharmacologic Class": "PharmacologicClass",
    "Side Effect": "SideEffect",
    "Symptom": "Symptom",
}

METAEDGE_NAMES = {
    "AdG": "Anatomy-downregulates-Gene",
    "AeG": "Anatomy-expresses-Gene",
    "AuG": "Anatomy-upregulates-Gene",
    "CbG": "Compound-binds-Gene",
    "CcSE": "Compound-causes-SideEffect",
    "CdG": "Compound-downregulates-Gene",
    "CpD": "Compound-palliates-Disease",
    "CrC": "Compound-resembles-Compound",
    "CtD": "Compound-treats-Disease",
    "CuG": "Compound-upregulates-Gene",
    "DaG": "Gene-associates-Disease",
    "DdG": "Disease-downregulates-Gene",
    "DlA": "Disease-localizes-Anatomy",
    "DpS": "Disease-presents-Symptom",
    "DrD": "Disease-resembles-Disease",
    "DuG": "Disease-upregulates-Gene",
    "GcG": "Gene-covaries-Gene",
    "GiG": "Gene-interacts-Gene",
    "GpBP": "Gene-participates-BiologicalProcess",
    "GpCC": "Gene-participates-CellularComponent",
    "GpMF": "Gene-participates-MolecularFunction",
    "GpPW": "Gene-participates-Pathway",
    "Gr>G": "Gene-regulates-Gene",
    "PCiC": "PharmacologicClass-includes-Compound",
}

FLIPPED_METAEDGES = {"DaG"}

STRING_ETYPE = "Gene-interacts-Gene"
TREATS_ETYPE = "Compound-treats-Disease"
